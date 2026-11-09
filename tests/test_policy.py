from copy import deepcopy

import pytest
from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.config import Config
from sborganize.model import Folder, Layout, fingerprint, validate_target
from sborganize.planner import Plan
from sborganize.policy import build_policy_plan, emoji_label
from sborganize.storage import layout_document, read_json, write_json
from sborganize.wire import prepare_device_plan


def icon(bundle, name):
    return {"bundleIdentifier": bundle, "displayName": name, "privateAppField": b"same"}


def folder(name, pages):
    return {"displayName": name, "iconLists": pages, "folderIdentity": name}


@pytest.fixture
def case():
    health = [icon(f"fitness.{i}", f"Fitness {i}") for i in range(12)]
    layout = Layout.from_raw(
        [
            [icon("dock", "Phone")],
            [
                {"listType": "widget", "widgetIdentifier": "synthetic", "payload": b"preserve"},
                folder("Bills", [[icon("energy", "Vattenfall")], [icon("phone", "KPN")]]),
                folder(
                    "🇨🇳",
                    [
                        [icon("bank", "招商银行")],
                        [icon("card", "掌上生活"), icon("hkbank", "ZA Bank")],
                    ],
                ),
                folder("Health", [health[:8], health[8:]]),
                folder("House", [[icon("repair", "Werkspot")]]),
                icon("parking", "EasyPark"),
            ],
        ]
    )
    folders = [
        {"id": "banks", "name": "🏦💰", "source": [1, 2], "target": [1, 1]},
        {"id": "bills", "name": "🧾💸", "source": [1, 1], "target": [1, 2]},
        {"id": "health", "name": "🩺🏃", "source": [1, 3], "target": [1, 3]},
        {"id": "home", "name": "🏠🛠️", "source": [1, 4], "target": [1, 4]},
    ]
    apps = {}
    for node in layout.apps():
        target = (
            "dock"
            if node.bundle_id == "dock"
            else "banks"
            if node.bundle_id in ("bank", "card", "hkbank")
            else "bills"
            if node.bundle_id in ("energy", "phone", "parking")
            else "home"
            if node.bundle_id == "repair"
            else "health"
        )
        apps[node.bundle_id] = {
            "name": node.name,
            "folder": target,
            "reason": "Explicitly reviewed primary function.",
        }
    policy = {
        "schema_version": 1,
        "kind": "organization_policy",
        "source_fingerprint": fingerprint(layout.raw),
        "folder_page_size": 9,
        "folders": folders,
        "apps": apps,
        "adjacent_groups": [["banks", "bills"]],
    }
    return layout, policy


def test_exhaustive_policy_overrides_regions_renames_orders_and_fills_pages(case):
    layout, policy = case
    original = deepcopy(layout.raw)
    plan, audit = build_policy_plan(layout, policy, Config(regions={"bank": "CN", "hkbank": "HK"}))
    ready = prepare_device_plan(plan)
    assert layout.raw == original
    assert ready.after.raw[0] == original[0] and ready.after.raw[1][0] == original[1][0]
    assert ready.after.raw[1][1]["displayName"] == "🏦💰"
    assert ready.after.raw[1][2]["displayName"] == "🧾💸"
    assert [a["displayName"] for p in ready.after.raw[1][1]["iconLists"] for a in p] == [
        "招商银行",
        "掌上生活",
        "ZA Bank",
    ]
    assert list(map(len, ready.after.raw[1][3]["iconLists"])) == [9, 3]
    assert [a["displayName"] for a in ready.after.raw[1][4]["iconLists"][0]] == ["Werkspot"]
    assert audit["complete"] and audit["app_count"] == len(layout.apps())
    assert audit["model_requests"] == 0 and len(audit["apps"]) == len(policy["apps"])
    for _, node in ready.after.walk():
        if isinstance(node, Folder):
            assert emoji_label(node.name)
            assert all(len(page) == 9 for page in node.pages[:-1])
    validate_target(layout, ready.after, folder_edits=ready.folder_edits)
    with pytest.raises(ValueError, match="folder"):
        validate_target(layout, ready.after)  # Default mode remains conservative.
    assert Plan.from_dict(ready.to_dict(Config())).after.raw == ready.after.raw
    assert any(c["kind"] == "rename" for c in ready.changes)
    assert any(c["kind"] == "folder-move" for c in ready.changes)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_app",
        "extra_app",
        "wrong_name",
        "no_reason",
        "text_folder",
        "duplicate_source",
        "opaque_slot",
        "stale",
        "unknown_target",
        "bad_rank",
        "not_adjacent",
    ],
)
def test_invalid_or_incomplete_policy_refused(case, mutation):
    layout, policy = case
    policy = deepcopy(policy)
    if mutation == "missing_app":
        policy["apps"].pop("bank")
    elif mutation == "extra_app":
        policy["apps"]["not-installed"] = policy["apps"]["bank"]
    elif mutation == "wrong_name":
        policy["apps"]["bank"]["name"] = "Other app"
    elif mutation == "no_reason":
        policy["apps"]["bank"]["reason"] = ""
    elif mutation == "text_folder":
        policy["folders"][0]["name"] = "Finance 🏦"
    elif mutation == "duplicate_source":
        policy["folders"][1]["source"] = [1, 2]
    elif mutation == "opaque_slot":
        policy["folders"][0]["target"] = [1, 0]
    elif mutation == "stale":
        policy["source_fingerprint"] = "old"
    elif mutation == "unknown_target":
        policy["apps"]["bank"]["folder"] = ["bad type"]
    elif mutation == "bad_rank":
        policy["apps"]["bank"]["rank"] = True
    else:
        policy["adjacent_groups"] = [["banks", "health"]]
    with pytest.raises(ValueError):
        build_policy_plan(layout, policy, Config())


def test_policy_cannot_move_dock_pins_or_change_arbitrary_folder_metadata(case):
    layout, policy = case
    bad = deepcopy(policy)
    bad["apps"]["dock"]["folder"] = "banks"
    with pytest.raises(ValueError, match="dock or pinned"):
        build_policy_plan(layout, bad, Config())
    with pytest.raises(ValueError, match="pins or unsupported"):
        build_policy_plan(layout, policy, Config(pins=("bank",)))
    plan, _ = build_policy_plan(layout, policy, Config())
    raw = plan.after.to_raw()
    raw[1][1]["folderIdentity"] = "corrupted"
    with pytest.raises(ValueError, match="metadata"):
        validate_target(layout, Layout.from_raw(raw), folder_edits=plan.folder_edits)
    raw = plan.after.to_raw()
    raw[1][0]["payload"] = b"changed"
    with pytest.raises(ValueError, match="unknown"):
        validate_target(layout, Layout.from_raw(raw), folder_edits=plan.folder_edits)


def test_folder_edits_need_explicit_unique_valid_declarations(case):
    layout, policy = case
    plan, _ = build_policy_plan(layout, policy, Config())
    for edits in (
        (),
        (plan.folder_edits[0], plan.folder_edits[0]),
        ({"source": [0, 0], "target": [1, 1], "name": "🏦"},),
    ):
        with pytest.raises(ValueError):
            validate_target(layout, plan.after, folder_edits=edits)


def test_policy_cli_full_safety_flow_stays_offline_and_preserves_input(case, tmp_path, monkeypatch):
    layout, policy = case
    source, mapping = tmp_path / "source.json", tmp_path / "policy.json"
    write_json(source, layout_document(layout))
    write_json(mapping, policy)
    before = source.read_bytes()
    monkeypatch.setattr("socket.socket.connect", lambda *a: pytest.fail("No network"))
    monkeypatch.setattr("sborganize.cli.cloud_provider", lambda *a: pytest.fail("No cloud"))
    monkeypatch.setattr("sborganize.apple.AppleProvider.probe", lambda *a: pytest.fail("No Apple"))
    runner = CliRunner()
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(
        app,
        [
            *prefix,
            "plan",
            "--policy",
            str(mapping),
            "--fixture",
            str(source),
            "--device-ready",
            "--no-network",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert "rename" in result.stdout
    target = tmp_path / "plans/domain-policy.json"
    assert not (tmp_path / "plans/latest.json").exists()
    assert read_json(tmp_path / "reviews/domain-policy-audit.json")["complete"]
    result = runner.invoke(
        app, [*prefix, "apply", "--fixture", str(source), "--plan", str(target), "--yes"]
    )
    assert result.exit_code == 0, result.exception
    assert "Simulation verified" in result.stdout
    assert source.read_bytes() == before


@pytest.mark.parametrize("label", ["🏦💰", "🇭🇰", "📚☁️", "🏃‍♂️", "🛍️🍔📦"])
def test_multiple_emoji_and_variation_sequences_are_valid(label):
    assert emoji_label(label)
