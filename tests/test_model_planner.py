import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from sborganize.cli import demo_layout
from sborganize.config import Config, load_config
from sborganize.model import (
    Folder,
    Icon,
    Layout,
    Opaque,
    decode_state,
    encode_state,
    fingerprint,
    parse_slot,
    validate_target,
)
from sborganize.planner import Plan, build_plan
from sborganize.score import score_layout
from sborganize.storage import layout_document, layout_from_document, read_json, write_json


def app(bundle, name="App", **extra):
    return {"bundleIdentifier": bundle, "displayName": name, **extra}


def test_lossless_plist_and_json_storage(tmp_path):
    raw = [
        [app("phone")],
        [
            None,
            False,
            0,
            {"listType": "future", "data": b"\x00\xff", "date": datetime(2025, 1, 1)},
            42,
        ],
    ]
    layout = Layout.from_raw(raw)
    assert layout.to_raw() == raw
    assert decode_state(encode_state(raw)) == raw
    path = tmp_path / "layout.json"
    write_json(path, layout_document(layout))
    assert layout_from_document(read_json(path)).raw == raw
    assert path.stat().st_mode & 0o777 == 0o600


def test_parse_folder_and_unknown_nodes():
    assert isinstance(parse_slot({"listType": "widget", "bundleIdentifier": "weather"}), Opaque)
    assert isinstance(parse_slot({"displayName": "Bad", "iconLists": ["invalid"]}), Opaque)
    assert isinstance(parse_slot({"listType": "future", "iconLists": [[]]}), Opaque)
    assert isinstance(
        parse_slot({"bundleIdentifier": "a", "listType": "icon", "iconType": "widget"}), Opaque
    )
    assert isinstance(parse_slot({"bundleIdentifier": "a", "widgetKind": "weather"}), Opaque)
    folder = parse_slot({"displayName": "Work", "iconLists": [[app("a")]]})
    assert isinstance(folder, Folder)
    assert isinstance(folder.pages[0][0], Icon)


def test_planner_preserves_inventory_unknowns_dock_and_improves_score(layout):
    untouched = layout.to_raw()
    config = Config()
    plan = build_plan(layout, config)
    assert layout.raw == untouched
    assert plan.after.raw[0] == untouched[0]
    assert plan.after.raw[1][2] == untouched[1][2]
    assert len(plan.after.apps()) == 28
    assert len(plan.after.pages) == 3
    assert score_layout(layout, config).value == 26
    assert score_layout(plan.after, config).value == 81
    validate_target(layout, plan.after)
    assert plan.to_dict(config) == build_plan(layout, config).to_dict(config)
    assert build_plan(plan.after, config).changes == []


def test_pins_in_folder_freeze_folder_and_loose_pins_stay(layout):
    config = Config(pins=("ph.telegra.Telegraph", "com.booking.BookingApp"))
    plan = build_plan(layout, config)
    assert plan.after.raw[1][0] == layout.raw[1][0]
    assert plan.after.raw[4][1] == layout.raw[4][1]
    assert len(plan.after.pages) == 4
    validate_target(layout, plan.after, config.pins)


def test_unknown_in_folder_blocks_compaction_and_reuse():
    folder = {"displayName": "Social", "iconLists": [[{"future": True}], []]}
    layout = Layout.from_raw([[], [folder, app("net.whatsapp.WhatsApp", "WhatsApp")]])
    plan = build_plan(layout, Config())
    assert plan.after.raw == layout.raw


def test_threshold_and_category_override():
    raw = [[], [app("a"), app("b")]]
    layout = Layout.from_raw(raw)
    assert not build_plan(layout, Config(categories={"a": "Tools", "b": "Tools"})).changes
    config = Config(
        new_folder_min_apps=2, categories={"a": "Tools", "b": "Tools"}, folders={"Tools": "Daily"}
    )
    plan = build_plan(layout, config)
    assert plan.after.raw[1][0]["displayName"] == "Daily"
    assert len(plan.after.apps()) == 2


def test_only_trailing_empty_pages_removed_and_unknown_holes_kept():
    raw = [[], [], [False, 0, {"future": True}], []]
    plan = build_plan(Layout.from_raw(raw), Config())
    assert plan.after.raw == raw[:-1]


@pytest.mark.parametrize("mutation", ["delete", "dock", "unknown", "payload", "folder"])
def test_validator_rejects_corrupt_targets(layout, mutation):
    raw = layout.to_raw()
    if mutation == "delete":
        raw[1][3] = None
    elif mutation == "dock":
        raw[0].reverse()
    elif mutation == "unknown":
        raw[1][2]["size"]["width"] = 2
    elif mutation == "payload":
        raw[1][3]["demoMetadata"] = {"changed": True}
    else:
        raw[1][0]["demoFolderID"] = "changed"
    with pytest.raises(ValueError):
        validate_target(layout, Layout.from_raw(raw))


def test_duplicate_bundle_ids_are_preserved_and_diffed():
    icon = app("net.whatsapp.WhatsApp", "WhatsApp")
    raw = [[], [deepcopy(icon), deepcopy(icon), deepcopy(icon)]]
    plan = build_plan(Layout.from_raw(raw), Config())
    assert len(plan.after.apps()) == 3
    assert len([c for c in plan.changes if c["kind"] == "move"]) == 3


def test_plan_export_import_validates_integrity(layout):
    data = build_plan(layout, Config()).to_dict(Config())
    plan = Plan.from_dict(json.loads(json.dumps(data)))
    assert fingerprint(plan.after.raw) == data["target_fingerprint"]
    data["target_fingerprint"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        Plan.from_dict(data)


def test_fingerprint_ignores_dictionary_key_order():
    assert fingerprint([[{"a": 1, "b": 2}]]) == fingerprint([[{"b": 2, "a": 1}]])


def test_packaged_demo_matches_repository_fixture():
    raw = read_json(Path(__file__).parents[1] / "fixtures/demo_layout.json")
    assert demo_layout().raw == layout_from_document(raw).raw


def test_config_load_and_bounds(tmp_path):
    path = tmp_path / "config.toml"
    assert load_config(path) == Config()
    path.write_text(
        '[pins]\nbundle_ids = ["a"]\n[folders.map]\nSocial = "Friends"\n'
        '[categories]\n"local.app" = "Social"\n'
    )
    assert load_config(path).pins == ("a",)
    assert load_config(path).categories == {"local.app": "Social"}
    for invalid in ["0", "true", '"9"', "1000"]:
        path.write_text(f"[planner]\nfolder_page_size = {invalid}\n")
        with pytest.raises(ValueError):
            load_config(path)
    path.write_text("pins = []\n")
    with pytest.raises(ValueError, match="TOML table"):
        load_config(path)
    path.write_text("[planner]\ncreate_folders = false\n")
    assert load_config(path).create_folders is False
    path.write_text('[planner]\ncreate_folders = "no"\n')
    with pytest.raises(ValueError, match="true or false"):
        load_config(path)


def test_empty_layout_score_bounded():
    for raw in [[[]], [[], []], [[], [None, 0, False]]]:
        assert 0 <= score_layout(Layout.from_raw(raw), Config()).value <= 100


def test_invalid_layout_rejected():
    for raw in [None, {}, [], ["page"], {"icon_state": []}]:
        with pytest.raises(ValueError):
            Layout.from_raw(raw)


def test_storage_creates_private_ancestor_directories(tmp_path):
    path = tmp_path / "private" / "backups" / "example.json"
    write_json(path, {"ok": True})
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.parent.parent.stat().st_mode & 0o777 == 0o700
