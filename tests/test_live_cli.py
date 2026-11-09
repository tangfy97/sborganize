from contextlib import asynccontextmanager

from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.config import Config
from sborganize.device import FixtureDevice
from sborganize.model import Layout
from sborganize.planner import build_plan
from sborganize.safety import load_backup
from sborganize.storage import write_json
from sborganize.wire import prepare_device_plan

runner = CliRunner()


def setup_phone(tmp_path, monkeypatch):
    source = Layout.from_raw(
        [
            [],
            [
                {"displayName": "Social", "iconLists": [[]]},
                {"bundleIdentifier": "example.whatsapp", "displayName": "WhatsApp"},
            ],
        ],
        "fake-trusted-phone",
        "usb",
    )
    config = Config(create_folders=False, compact_folders=False)
    plan = prepare_device_plan(build_plan(source, config))
    write_json(tmp_path / "plans/latest.json", plan.to_dict(config))

    class Phone(FixtureDevice):
        def __init__(self):
            super().__init__(source)
            self.source = "usb"
            self.writes = []

        async def write(self, raw):
            self.writes.append(raw)
            await super().write(raw)

    phone = Phone()

    @asynccontextmanager
    async def connect(udid, *, allow_write=False):
        assert allow_write is True
        assert udid in (None, "fake-trusted-phone")
        yield phone

    monkeypatch.setattr("sborganize.cli.connect_usb", connect)
    return source, plan, phone


def test_experimental_usb_apply_and_restore_share_safety_gate(tmp_path, monkeypatch):
    source, plan, phone = setup_phone(tmp_path, monkeypatch)
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(app, [*prefix, "apply", "--experimental-write", "--yes"])
    assert result.exit_code == 0, result.exception
    assert "No phone writes" not in result.stdout
    assert all(stage in result.stdout for stage in ("1/3", "2/3", "3/3"))
    assert phone.writes == [source.raw, plan.after.raw]
    backup = next((tmp_path / "backups").glob("*.json"))
    assert load_backup(backup).raw == source.raw
    result = runner.invoke(
        app, [*prefix, "restore", "--experimental-write", "--backup", str(backup), "--yes"]
    )
    assert result.exit_code == 0, result.exception
    assert phone.layout.raw == source.raw
    assert len(phone.writes) == 4


def test_real_confirmation_declined_has_zero_writes(tmp_path, monkeypatch):
    _, _, phone = setup_phone(tmp_path, monkeypatch)
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path), "apply", "--experimental-write"], input="n\n"
    )
    assert result.exit_code == 1
    assert phone.writes == []
    assert len(list((tmp_path / "backups").glob("*.json"))) == 1


def test_non_ready_plan_refused_before_usb_connection(tmp_path, monkeypatch):
    source, _, phone = setup_phone(tmp_path, monkeypatch)
    write_json(tmp_path / "plans/latest.json", build_plan(source, Config()).to_dict(Config()))
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path), "apply", "--experimental-write", "--yes"]
    )
    assert result.exit_code == 1
    assert phone.writes == [] and not (tmp_path / "backups").exists()
