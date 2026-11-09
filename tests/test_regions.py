import pytest

from sborganize.config import Config, load_config
from sborganize.model import Layout, parse_slot, validate_target
from sborganize.planner import Plan, build_plan, folder_categories
from sborganize.regions import app_region


def icon(bundle, name):
    return {"bundleIdentifier": bundle, "displayName": name}


def folder(name, *icons):
    return {"displayName": name, "iconLists": [list(icons)]}


def test_regions_take_priority_while_global_services_use_domain():
    layout = Layout.from_raw(
        [
            [],
            [
                folder("🇨🇳", icon("cn-peer", "Railway12306")),
                folder("HK", icon("hk-peer", "Octopus")),
                folder("🚌🚄", icon("maps", "Maps"), icon("uber", "Uber")),
                folder("✈️", icon("booking", "Booking"), icon("airbnb", "Airbnb")),
                folder("TV&AI", icon("chat", "ChatGPT"), icon("claude", "Claude")),
            ],
            [
                icon("com.xiaojukeji.didi", "DiDi"),
                icon("com.didi.global.passenger", "DiDi"),
                icon("hk-loose", "ZA Bank"),
                icon("royal", "Royal Jordanian"),
                icon("ai-loose", "Meta AI"),
                icon("cn.example.unknown", "未识别工具"),
            ],
        ]
    )
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    moved = {c["bundle_id"]: c["to"].split(",")[0] for c in plan.changes if c["kind"] == "move"}
    assert moved == {
        "com.xiaojukeji.didi": "🇨🇳",
        "com.didi.global.passenger": "🚌🚄",
        "hk-loose": "HK",
        "royal": "✈️",
        "ai-loose": "TV&AI",
    }
    assert plan.after.raw[2][-1] == layout.raw[2][-1]
    assert len(plan.unresolved) == 1
    validate_target(layout, plan.after)
    assert not build_plan(plan.after, config).changes


def test_regional_folders_are_excluded_from_global_domain_votes():
    cn = folder("🇨🇳", icon("maps", "Maps"), icon("uber", "Uber"))
    assert folder_categories(parse_slot(cn), Config()) == {"region:CN"}
    layout = Layout.from_raw([[], [cn, icon("global", "Royal Jordanian")]])
    plan = build_plan(layout, Config(create_folders=False))
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "no_matching_folder"


def test_regional_app_never_falls_back_when_region_folder_missing():
    layout = Layout.from_raw([[], [folder("Travel"), icon("com.xiaojukeji.didi", "DiDi")]])
    plan = build_plan(layout, Config(create_folders=False))
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "missing_regional_folder"
    assert plan.unresolved[0]["region"] == "CN"


def test_explicit_region_overrides_and_custom_folder_targets():
    layout = Layout.from_raw([[], [folder("Local"), folder("Travel"), icon("app", "Notion")]])
    config = Config(regions={"app": "HK"}, region_folders={"HK": "Local"}, create_folders=False)
    plan = build_plan(layout, config)
    assert plan.after.raw[1][0]["iconLists"][0][0] == layout.raw[1][2]
    assert (
        app_region(
            parse_slot(icon("com.xiaojukeji.didi", "DiDi")),
            Config(regions={"com.xiaojukeji.didi": "GLOBAL"}),
            {},
        )
        == "GLOBAL"
    )


def test_same_app_in_both_regional_groups_requires_review():
    one = icon("ambiguous", "Uncatalogued")
    layout = Layout.from_raw([[], [folder("🇨🇳", one), folder("HK", one), one]])
    plan = build_plan(layout, Config(create_folders=False))
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "conflicting_regions"


def test_learn_region_by_exact_bundle_not_publisher_prefix_or_script():
    peer = icon("com.example.known", "Uncatalogued")
    unrelated = icon("com.example.other", "另一个中文应用")
    layout = Layout.from_raw([[], [folder("HK", peer), peer, unrelated]])
    plan = build_plan(layout, Config(create_folders=False))
    assert plan.after.raw[1][1] is None
    assert plan.after.raw[1][2] == unrelated


def test_misplaced_regional_app_is_reported_without_relocating_existing_apps():
    raw = icon("com.xiaojukeji.didi", "DiDi")
    layout = Layout.from_raw([[], [folder("Travel", raw), folder("🇨🇳")]])
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    assert plan.after.raw == layout.raw
    assert plan.regional_review[0] == {
        "name": "DiDi",
        "bundle_id": "com.xiaojukeji.didi",
        "region": "CN",
        "from": "Travel",
        "reason": "kept_existing_position",
        "candidates": ["🇨🇳"],
    }
    assert Plan.from_dict(plan.to_dict(config)).regional_review == plan.regional_review


def test_regional_folder_protection_and_duplicate_targets():
    layout = Layout.from_raw(
        [[], [folder("🇨🇳", {"future": True}), icon("com.xiaojukeji.didi", "DiDi")]]
    )
    plan = build_plan(layout, Config())
    assert plan.after.raw == layout.raw
    assert plan.unresolved[0]["reason"] == "protected_folder"
    duplicate = Layout.from_raw(
        [[], [folder("🇨🇳"), folder("China"), icon("com.xiaojukeji.didi", "DiDi")]]
    )
    assert build_plan(duplicate, Config()).unresolved[0]["reason"] == "ambiguous_folders"
    chosen = build_plan(duplicate, Config(region_folders={"CN": "China"}))
    assert chosen.after.raw[1][1]["iconLists"][0][0]["displayName"] == "DiDi"


def test_region_config_validation(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[regions]\n"example" = "HK"\n[folders.regions]\nHK = "Local"\n')
    assert load_config(path).regions == {"example": "HK"}
    assert load_config(path).region_folders == {"HK": "Local"}
    for text in [
        '[regions]\n"a" = "China"',
        '[folders.regions]\nUS = "US"',
        '[folders.regions]\nCN = "HK"',
    ]:
        path.write_text(text)
        with pytest.raises(ValueError):
            load_config(path)


def test_global_variant_already_inside_region_folder_is_reviewed():
    raw = icon("com.didi.global.passenger", "DiDi")
    layout = Layout.from_raw([[], [folder("🇨🇳", raw)]])
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    assert plan.after.raw == layout.raw
    assert plan.regional_review[0]["region"] == "GLOBAL"
