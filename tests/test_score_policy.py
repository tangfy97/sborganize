from dataclasses import replace

import pytest

from sborganize.config import Config
from sborganize.model import Layout
from sborganize.planner import Plan, build_plan
from sborganize.render import render_plan, render_score
from sborganize.score import score_layout


def icon(bundle, name="Notion"):
    return {"bundleIdentifier": bundle, "displayName": name}


def test_existing_only_coverage_does_not_penalize_space_freed_by_grouping():
    peers = [icon(f"peer-{i}") for i in range(223)]
    folder = {"displayName": "Work", "iconLists": [peers[i : i + 9] for i in range(0, 223, 9)]}
    loose = [icon(f"loose-{i}") for i in range(11)] + [
        icon(f"unknown-{i}", "Uncatalogued") for i in range(6)
    ]
    layout = Layout.from_raw(
        [
            [icon(f"dock-{i}") for i in range(4)],
            [folder, {"widget": True}],
            [{"widget": True}],
            [{"widget": True}],
            loose,
        ]
    )
    config = Config(create_folders=False, compact_folders=False)
    plan = build_plan(layout, config)
    before, after = score_layout(layout, config), score_layout(plan.after, config)
    assert before.scope == after.scope == "grouping"
    assert before.value == 93 and after.value == 98
    assert before.counts == {"home_screen_apps": 240, "loose_apps": 17, "grouped_apps": 223}
    assert after.counts == {"home_screen_apps": 240, "loose_apps": 6, "grouped_apps": 234}
    # The complete layout score is retained, including its density trade-off.
    assert score_layout(plan.after, Config()).value < score_layout(layout, Config()).value
    assert "Grouping 93% → 98%" in render_plan(plan, before, after)
    assert "Grouping rate" in render_score(before)
    loaded = Plan.from_dict(plan.to_dict(config))
    assert loaded.create_folders is False and loaded.compact_folders is False
    assert loaded.to_dict(Config())["score_after"]["scope"] == "grouping"
    assert loaded.score_config(Config()) == config


@pytest.mark.parametrize(
    "raw, expected",
    [
        ([[]], 100),
        ([[], [icon("loose")]], 0),
        ([[], [{"displayName": "Work", "iconLists": [[icon("grouped")]]}]], 100),
    ],
)
def test_grouping_rate_endpoints(raw, expected):
    score = score_layout(Layout.from_raw(raw), Config(create_folders=False, compact_folders=False))
    assert score.value == expected
    assert score.scope == "grouping"
    assert "sparsity" not in score.penalties


def test_grouping_rate_excludes_dock_folder_apps():
    dock = [{"displayName": "Dock folder", "iconLists": [[icon("dock")]]}]
    score = score_layout(
        Layout.from_raw([dock, [icon("loose")]]),
        Config(create_folders=False, compact_folders=False),
    )
    assert score.value == 0 and score.counts["home_screen_apps"] == 1


def test_legacy_plan_defaults_and_invalid_policy(layout):
    data = build_plan(layout, Config()).to_dict(Config())
    data.pop("policy")
    loaded = Plan.from_dict(data)
    assert loaded.create_folders and loaded.compact_folders
    data["policy"] = {"compact_folders": "false"}
    with pytest.raises(ValueError, match="planning policy"):
        Plan.from_dict(data)


def test_renderer_rejects_mixed_metric_scopes(layout):
    plan = build_plan(layout, Config())
    with pytest.raises(ValueError, match="different scopes"):
        render_plan(
            plan,
            score_layout(layout, Config()),
            score_layout(layout, replace(Config(), create_folders=False, compact_folders=False)),
        )
