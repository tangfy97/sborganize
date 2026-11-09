import asyncio

import pytest

from sborganize.config import Config
from sborganize.device import FixtureDevice, USBDevice
from sborganize.model import Layout, fingerprint
from sborganize.planner import build_plan
from sborganize.safety import SafetyError, apply_target, backup_layout, load_backup


class RecordingDevice(FixtureDevice):
    def __init__(self, layout, fail_after=None, mismatch_after=None):
        super().__init__(layout)
        self.writes = []
        self.fail_after = fail_after
        self.mismatch_after = mismatch_after

    async def write(self, raw):
        self.writes.append(raw)
        if len(self.writes) == self.fail_after:
            raise OSError("Transport lost")
        await super().write(raw)
        if len(self.writes) == self.mismatch_after:
            changed = self.layout.to_raw()
            changed.append([])
            self.layout = Layout.from_raw(changed, self.udid, self.source)


def test_apply_backup_precedes_confirm_and_round_trip(layout, tmp_path):
    plan = build_plan(layout, Config())
    device = RecordingDevice(layout)

    def confirm(path):
        assert path.is_file()
        assert load_backup(path).raw == layout.raw
        assert not device.writes
        return True

    backup = asyncio.run(apply_target(device, layout, plan.after, tmp_path, confirm))
    assert device.writes == [layout.raw, plan.after.raw]
    assert load_backup(backup).raw == layout.raw
    assert device.layout.raw == plan.after.raw


def test_declining_confirmation_never_writes(layout, tmp_path):
    device = RecordingDevice(layout)
    with pytest.raises(SafetyError, match="Cancelled"):
        asyncio.run(
            apply_target(
                device, layout, build_plan(layout, Config()).after, tmp_path, lambda p: False
            )
        )
    assert not device.writes
    assert len(list((tmp_path / "backups").glob("*.json"))) == 1


def test_stale_plan_and_wrong_device_rejected_before_backup(layout, tmp_path):
    plan = build_plan(layout, Config())
    changed = Layout.from_raw([*layout.raw, []], layout.udid)
    for current in [changed, Layout.from_raw(layout.raw, "another-device")]:
        device = RecordingDevice(current)
        with pytest.raises(SafetyError):
            asyncio.run(apply_target(device, layout, plan.after, tmp_path, lambda p: True))
        assert not device.writes
        assert not (tmp_path / "backups").exists()


def test_confirmation_race_rejected(layout, tmp_path):
    device = RecordingDevice(layout)

    def confirm(path):
        device.layout = Layout.from_raw([*layout.raw, []], layout.udid)
        return True

    with pytest.raises(SafetyError, match="during confirmation"):
        asyncio.run(
            apply_target(device, layout, build_plan(layout, Config()).after, tmp_path, confirm)
        )
    assert not device.writes


@pytest.mark.parametrize(
    "mismatch_after, message, writes",
    [
        (1, "round-trip mismatch", 1),
        (2, "Read-back mismatch", 2),
    ],
)
def test_mismatches_abort_and_report_backup(layout, tmp_path, mismatch_after, message, writes):
    device = RecordingDevice(layout, mismatch_after=mismatch_after)
    with pytest.raises(SafetyError, match=message) as error:
        asyncio.run(
            apply_target(
                device, layout, build_plan(layout, Config()).after, tmp_path, lambda p: True
            )
        )
    assert len(device.writes) == writes
    assert "Backup kept:" in str(error.value)
    backup = next((tmp_path / "backups").glob("*.json"))
    assert load_backup(backup).raw == layout.raw


@pytest.mark.parametrize("fail_after", [1, 2])
def test_transport_failure_keeps_backup(layout, tmp_path, fail_after):
    device = RecordingDevice(layout, fail_after=fail_after)
    with pytest.raises(SafetyError, match="Transport lost.*Backup kept"):
        asyncio.run(
            apply_target(
                device, layout, build_plan(layout, Config()).after, tmp_path, lambda p: True
            )
        )
    assert len(device.writes) == fail_after
    assert next((tmp_path / "backups").glob("*.json")).is_file()


def test_backup_failure_blocks_confirmation_and_writes(layout, tmp_path):
    root = tmp_path / "not-a-directory"
    root.write_text("blocked")
    device = RecordingDevice(layout)

    def confirm(path):
        pytest.fail("Must not confirm without backup")

    with pytest.raises(OSError):
        asyncio.run(apply_target(device, layout, build_plan(layout, Config()).after, root, confirm))
    assert not device.writes


def test_restore_recovers_exact_raw(layout, tmp_path):
    path = backup_layout(layout, tmp_path)
    plan = build_plan(layout, Config())
    device = RecordingDevice(plan.after)
    restored_backup = asyncio.run(
        apply_target(
            device,
            plan.after,
            load_backup(path),
            tmp_path,
            lambda p: True,
            restore=True,
        )
    )
    assert device.layout.raw == layout.raw
    assert fingerprint(load_backup(restored_backup).raw) == fingerprint(plan.after.raw)


def test_live_usb_write_adapter_always_refuses():
    class Lockdown:
        udid = "real-device"

    device = USBDevice(Lockdown(), object())
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(device.write([[]]))


def test_enabled_usb_write_calls_our_pymobiledevice_service_only():
    class Lockdown:
        udid = "fake-usb"

    class Service:
        def __init__(self):
            self.writes = []

        async def set_icon_state(self, raw):
            self.writes.append(raw)

    service = Service()
    device = USBDevice(Lockdown(), service, allow_write=True)
    asyncio.run(device.write([[], []]))
    assert service.writes == [[[], []]]
    with pytest.raises(ValueError, match="cannot be encoded"):
        asyncio.run(device.write([[], [None]]))
    assert len(service.writes) == 1


def test_corrupted_backup_blocks_confirmation_and_all_writes(layout, tmp_path, monkeypatch):
    path = backup_layout(layout, tmp_path)
    path.write_text('{"kind": "backup", "schema_version": 1}')
    monkeypatch.setattr("sborganize.safety.backup_layout", lambda *a: path)
    device = RecordingDevice(layout)
    with pytest.raises((ValueError, KeyError, SafetyError)):
        asyncio.run(
            apply_target(
                device,
                layout,
                build_plan(layout, Config()).after,
                tmp_path,
                lambda p: pytest.fail("Must not confirm bad backup"),
            )
        )
    assert not device.writes


@pytest.mark.parametrize("change", ["widget_field_removed", "app_added"])
def test_live_roundtrip_regressions_stop_before_target_write(tmp_path, change):
    layout = Layout.from_raw(
        [
            [],
            [
                {
                    "listType": "widget",
                    "widgetIdentifier": "synthetic-widget",
                    "userSelectedElementIdentifier": "synthetic-selected-element",
                },
                {"bundleIdentifier": "synthetic.app", "displayName": "App"},
            ],
        ]
    )

    class ChangedBySystem(RecordingDevice):
        async def write(self, raw):
            await super().write(raw)
            changed = self.layout.to_raw()
            if change == "widget_field_removed":
                changed[1][0].pop("userSelectedElementIdentifier")
            else:
                changed[1].append({"bundleIdentifier": "synthetic.added", "displayName": "New"})
            self.layout = Layout.from_raw(changed, self.udid, self.source)

    device = ChangedBySystem(layout)
    with pytest.raises(SafetyError, match="round-trip mismatch.*Target was not written"):
        asyncio.run(apply_target(device, layout, layout, tmp_path, lambda p: True))
    assert len(device.writes) == 1
    assert load_backup(next((tmp_path / "backups").glob("*.json"))).raw == layout.raw
