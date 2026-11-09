from pathlib import Path

import pytest

from sborganize.config import Config
from sborganize.model import Folder, Layout, parse_slot, validate_target
from sborganize.planner import Plan, build_plan, folder_categories, loose_count
from sborganize.storage import layout_from_document, read_json


def icon(bundle, name):
    return {"bundleIdentifier": bundle, "displayName": name}


def folder(name, *apps):
    return {"listType": "folder", "displayName": name, "iconLists": [list(apps)]}


def test_synthetic_mixed_emoji_folders_reuse_existing_groups_without_creating():
    path = Path(__file__).parents[1] / "fixtures/emoji_folders.json"
    layout = layout_from_document(read_json(path))
    config = Config(create_folders=False)
    plan = build_plan(layout, config)
    assert loose_count(layout) == 8
    assert loose_count(plan.after) == 2
    assert len([n for _, n in layout.walk() if isinstance(n, Folder)]) == len(
        [n for _, n in plan.after.walk() if isinstance(n, Folder)]
    )
    assert plan.after.raw[1][8] == layout.raw[1][8]
    assert {c["name"]: c["to"].split(",")[0] for c in plan.changes if c["kind"] == "move"} == {
        "Notion": "📃",
        "Authenticator": "📃",
        "IBKR": "💰",
        "IMDb": "🎬🎵",
        "Meta AI": "TV&AI",
        "Njoy Fitness App": "🏃🏻",
    }
    review = {item["name"]: item for item in plan.unresolved}
    assert review["DiDi"]["reason"] == "ambiguous_folders"
    assert review["DiDi"]["candidates"] == ["🚌🚄", "✈️"]
    assert review["Uncatalogued"]["reason"] == "unknown_category"
    assert plan.after.raw[2][6:] == layout.raw[2][6:]
    validate_target(layout, plan.after)
    assert build_plan(plan.after, config).after.raw == plan.after.raw
    exported = plan.to_dict(config)
    assert exported["loose_before"] == 8 and exported["loose_after"] == 2
    assert exported["policy"]["create_folders"] is False
    assert Plan.from_dict(exported).unresolved == plan.unresolved


def test_repeated_same_app_does_not_manufacture_folder_evidence():
    raw = folder("🧩", icon("same", "Notion"), icon("same", "Notion"))
    node = parse_slot(raw)
    assert not folder_categories(node, Config())
    raw["iconLists"][0].append(icon("another", "Todoist"))
    assert folder_categories(parse_slot(raw), Config()) == {"Productivity"}


def test_empty_and_unrecognized_folder_have_no_inferred_roles():
    for raw in [folder("🧩"), folder("🧩", icon("one", "Uncatalogued"))]:
        assert not folder_categories(parse_slot(raw), Config())


def test_single_category_peer_cannot_redirect_mixed_folder():
    raw = folder("🧩", icon("a", "Revolut"), icon("b", "PayPal"), icon("c", "Maps"))
    assert folder_categories(parse_slot(raw), Config()) == {"Finance"}


def test_named_folder_roles_override_incidental_contents():
    raw = folder("Utilities", icon("a", "Notes"), icon("b", "Reminders"))
    assert folder_categories(parse_slot(raw), Config()) == {"Utilities"}
    config = Config(folders={"Personal": "Utilities", "Work": "Utilities"})
    assert folder_categories(parse_slot(raw), config) == {"Utilities", "Personal", "Work"}


@pytest.mark.parametrize("names", [("Social", "Friends"), ("💬", "🗨️")])
def test_multiple_matching_folders_abstain_until_explicit_map(names):
    one = folder(names[0], icon("a", "Signal"), icon("b", "Telegram"))
    two = folder(names[1], icon("c", "WhatsApp"), icon("d", "Instagram"))
    layout = Layout.from_raw([[], [one, two, icon("loose", "WhatsApp")]])
    plan = build_plan(layout, Config())
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "ambiguous_folders"
    mapped = build_plan(layout, Config(folders={"Social": names[1]}))
    assert len(mapped.after.raw[1][1]["iconLists"][0]) == 3
    assert mapped.after.raw[1][2] is None


def test_inferred_protected_folder_never_receives_apps():
    raw = folder("💬", icon("a", "Signal"), icon("b", "Telegram"), {"future": True})
    layout = Layout.from_raw([[], [raw, icon("loose", "WhatsApp")]])
    plan = build_plan(layout, Config())
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "protected_folder"


def test_existing_only_keeps_category_group_without_creating_folder():
    raw = [[], [icon("a", "Signal"), icon("b", "Telegram"), icon("c", "WhatsApp")]]
    layout = Layout.from_raw(raw)
    plan = build_plan(layout, Config(create_folders=False))
    assert plan.after.raw == raw
    assert all(item["reason"] == "no_matching_folder" for item in plan.unresolved)
    assert any(c["kind"] == "folder+" for c in build_plan(layout, Config()).changes)


def test_configured_missing_folder_does_not_fall_back_to_unrequested_folder():
    raw = folder("Social", icon("a", "Signal"), icon("b", "Telegram"))
    layout = Layout.from_raw([[], [raw, icon("loose", "WhatsApp")]])
    config = Config(folders={"Social": "Missing"}, create_folders=False)
    plan = build_plan(layout, config)
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "no_matching_folder"


def test_conservative_mode_fills_holes_without_repacking_existing_apps():
    raw = {
        "listType": "folder",
        "displayName": "💬",
        "iconLists": [
            [icon("a", "Signal"), None],
            [icon("b", "Telegram")],
        ],
    }
    layout = Layout.from_raw([[], [raw, icon("loose", "WhatsApp")]])
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    assert plan.after.raw[1][0]["iconLists"][0][0] == raw["iconLists"][0][0]
    assert plan.after.raw[1][0]["iconLists"][1][0] == raw["iconLists"][1][0]
    assert plan.after.raw[1][0]["iconLists"][0][1] == layout.raw[1][1]
    assert [c["name"] for c in plan.changes if c["kind"] == "move"] == ["WhatsApp"]


def test_new_custom_folder_mapping_keeps_learnt_roles():
    raw = folder("💬", icon("a", "Signal"), icon("b", "Telegram"))
    config = Config(folders={"Personal": "💬"})
    assert folder_categories(parse_slot(raw), config) == {"Personal", "Social"}


@pytest.mark.parametrize("capacity", [9, 18])
def test_conservative_append_preserves_full_observed_pages(capacity):
    raw = folder("💬", *(icon(f"peer-{i}", "Signal") for i in range(capacity)))
    layout = Layout.from_raw(
        [
            [],
            [
                raw,
                icon("loose-1", "WhatsApp"),
                icon("loose-2", "Instagram"),
                icon("loose-3", "Telegram"),
            ],
        ]
    )
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    pages = plan.after.raw[1][0]["iconLists"]
    assert pages[0] == raw["iconLists"][0]
    assert [len(page) for page in pages] == [capacity, 3]
    assert loose_count(plan.after) == 0
    validate_target(layout, plan.after)
