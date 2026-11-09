from datetime import datetime

import pytest

from sborganize.config import Config
from sborganize.model import Layout, structural_fingerprint, validate_target
from sborganize.planner import Plan, build_plan
from sborganize.wire import prepare_device_plan, validate_wire_state


def icon(bundle, name="WhatsApp"):
    return {"bundleIdentifier": bundle, "displayName": name}


def test_device_ready_compacts_only_after_original_anchors():
    raw = [
        [],
        [
            {"listType": "widget", "data": [1, 2]},
            {"displayName": "Social", "iconLists": [[]]},
            icon("move"),
            icon("keep", "Uncatalogued"),
        ],
    ]
    layout = Layout.from_raw(raw)
    config = Config(create_folders=False, compact_folders=False)
    preview = build_plan(layout, config)
    ready = prepare_device_plan(preview)
    assert ready.after.raw[1][0] == raw[1][0]
    assert ready.after.raw[1][1]["displayName"] == "Social"
    assert ready.after.raw[1][2] == raw[1][3]
    assert ready.device_ready
    assert Plan.from_dict(ready.to_dict(config)).device_ready
    validate_wire_state(ready.after.raw)
    validate_target(layout, ready.after)


def test_anchored_gap_is_refused_instead_of_inventing_usb_marker():
    layout = Layout.from_raw([[], [icon("move"), {"displayName": "Social", "iconLists": [[]]}]])
    preview = build_plan(layout, Config())
    with pytest.raises(ValueError, match="cannot be encoded"):
        prepare_device_plan(preview)


def test_pins_are_anchors_for_device_ready_compaction():
    layout = Layout.from_raw(
        [[], [{"displayName": "Social", "iconLists": [[]]}, icon("move"), icon("pin", "Pinned")]]
    )
    preview = build_plan(layout, Config(pins=("pin",)))
    with pytest.raises(ValueError, match="cannot be encoded"):
        prepare_device_plan(preview)


def test_structural_verification_ignores_only_known_app_bookkeeping():
    raw = [[icon("dock")], [{"listType": "widget", "iconModDate": 1}, icon("app")]]
    changed = Layout.from_raw(raw).to_raw()
    changed[0][0]["iconModDate"] = datetime(2026, 1, 1)
    changed[1][1]["bundleVersion"] = "2"
    assert structural_fingerprint(raw) == structural_fingerprint(changed)
    changed[1][0]["iconModDate"] = 2
    assert structural_fingerprint(raw) != structural_fingerprint(changed)


def test_restore_retains_pins_dock_and_inventory_despite_bookkeeping_changes():
    raw = [[icon("dock")], [icon("pin")]]
    current = Layout.from_raw(raw)
    target = current.to_raw()
    target[0][0]["bundleVersion"] = "older"
    target[1][0]["iconModDate"] = datetime(2026, 1, 1)
    validate_target(current, Layout.from_raw(target), ("pin",), restore=True)
    target[1][0]["displayName"] = "Different app name"
    with pytest.raises(ValueError):
        validate_target(current, Layout.from_raw(target), ("pin",), restore=True)
