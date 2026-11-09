from copy import deepcopy

import pytest
from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.config import Config
from sborganize.model import Layout, validate_target
from sborganize.planner import Plan, build_plan
from sborganize.reorganization import build_reorganization, refresh_reorganization
from sborganize.review import recheck_report, review_layout
from sborganize.storage import layout_document, read_json, write_json
from sborganize.wire import prepare_device_plan


def icon(bundle, name="App"):
    return {"bundleIdentifier": bundle, "displayName": name}


def folder(name, *children):
    return {"displayName": name, "iconLists": [list(children)], "marker": name}


class Provider:
    def __init__(self, decide=None):
        self.decide = decide or (lambda record, folders: {})

    def review_batch(self, request):
        import json

        payload = json.loads(request["prompt"])
        return {
            "placements": {
                record["app_id"]: {
                    "purpose_known": False,
                    "domain": "unknown",
                    "region": "unknown",
                    "confidence": "low",
                    "target": "keep",
                    "reason": "Purpose unclear.",
                    **self.decide(record, payload["folders"]),
                }
                for record in payload["apps"]
            }
        }


def cloud(layout, config, root, decide=None):
    return review_layout(
        layout, config, root, cloud=True, provider_factory=lambda: Provider(decide)
    )


def test_explicit_prototypes_group_and_unknown_nodes_dock_pins_survive(tmp_path):
    layout = Layout.from_raw(
        [
            [icon("dock")],
            [
                {"listType": "future", "data": b"untouched"},
                folder("Finance", icon("peer", "Revolut")),
                icon("pin"),
                *[icon(f"self.{i}", f"Prototype {i}") for i in range(4)],
            ],
            [icon("com.go-jek.gopay", "GoPay")],
        ]
    )
    config = Config(
        pins=("pin",),
        folders={"Development": "Test", "Finance": "Finance"},
        categories={f"self.{i}": "Development" for i in range(4)},
    )
    report = cloud(layout, config, tmp_path)
    raw = deepcopy(layout.raw)
    plan = prepare_device_plan(build_reorganization(layout, report, config))
    validate_target(layout, plan.after, config.pins)
    assert layout.raw == raw and len(plan.after.apps()) == len(layout.apps())
    assert plan.device_ready and len(plan.after.pages) == 1
    test = next(n for _, n in plan.after.walk() if getattr(n, "name", None) == "Test")
    assert sorted(child.bundle_id for page in test.pages for child in page) == [
        f"self.{i}" for i in range(4)
    ]
    assert len(plan.smart_info["accepted"]) == 5
    assert Plan.from_dict(plan.to_dict(config)).after.raw == plan.after.raw


def test_known_identity_and_region_override_bad_cloud_suggestion(tmp_path):
    layout = Layout.from_raw(
        [
            [],
            [
                folder("Health", icon("nl.cz.app", "CZ"), icon("health-peer", "Fitness")),
                folder("Finance", icon("finance-peer", "PayPal")),
                folder("Travel", icon("travel-peer", "Maps")),
                folder("🇨🇳", icon("cn-peer", "Meituan")),
                icon("com.go-jek.gopay", "GoPay"),
            ],
        ]
    )
    config = Config(folders={"Health": "Health", "Finance": "Finance"})

    def bad(record, folders):
        name = "Travel" if record["name"] == "CZ" else "🇨🇳"
        return {
            "purpose_known": True,
            "domain": "Transport" if name == "Travel" else "Finance",
            "region": "GLOBAL" if name == "Travel" else "CN",
            "confidence": "high",
            "target": next(f["id"] for f in folders if f["name"] == name),
        }

    report = cloud(layout, config, tmp_path, bad)
    rows = {row["name"]: row for row in report["apps"]}
    assert rows["CZ"]["status"] == rows["GoPay"]["status"] == "review"
    plan = build_reorganization(layout, report, config)
    assert plan.after.raw[1][0] == layout.raw[1][0]  # CZ remains Health, not transport.
    assert plan.after.raw[1][1]["iconLists"][0][-1]["bundleIdentifier"] == "com.go-jek.gopay"


def test_destination_semantics_and_unverified_regions_are_not_accepted(tmp_path):
    layout = Layout.from_raw(
        [[], [folder("Home"), folder("Weather"), icon("browser", "Browser"), icon("tool", "Tool")]]
    )
    config = Config(folders={"Home": "Home", "Weather": "Weather"})

    def bad(record, folders):
        return {
            "purpose_known": True,
            "confidence": "high",
            "domain": "Web",
            "region": "GLOBAL" if record["name"] == "Browser" else "CN",
            "target": next(f["id"] for f in folders if f["name"] == "Home"),
        }

    report = cloud(layout, config, tmp_path, bad)
    assert report["counts"]["move"] == 0 and report["counts"]["review"] == 2


def test_empty_existing_folder_refused_instead_of_removing_it(tmp_path):
    layout = Layout.from_raw(
        [
            [],
            [
                folder("Wrong", icon("com.go-jek.gopay", "GoPay")),
                folder("Finance", icon("peer", "PayPal")),
            ],
        ]
    )
    config = Config()
    report = cloud(layout, config, tmp_path)
    with pytest.raises(ValueError, match="empty an existing folder"):
        build_reorganization(layout, report, config)


def test_regrouping_trims_only_newly_empty_trailing_folder_pages(tmp_path):
    source = folder("Mixed", icon("stay", "Unclassified"))
    source["iconLists"].append([icon("com.go-jek.gopay", "GoPay")])
    untouched = folder("Untouched", icon("peer", "Unclassified"))
    untouched["iconLists"].append([])
    layout = Layout.from_raw([[], [source, folder("Finance", icon("bank", "PayPal")), untouched]])
    config = Config()
    report = cloud(layout, config, tmp_path)
    plan = build_reorganization(layout, report, config)
    assert list(map(len, plan.after.raw[1][0]["iconLists"])) == [1]
    assert plan.after.raw[1][2] == layout.raw[1][2]
    validate_target(layout, plan.after)


@pytest.mark.parametrize("tamper", ["source", "app", "candidate_binding", "incomplete"])
def test_recheck_rejects_stale_or_misbound_advice(tmp_path, tamper):
    layout = Layout.from_raw([[], [icon("one"), icon("two")]])
    config = Config()
    report = cloud(layout, config, tmp_path)
    if tamper == "source":
        report["source_fingerprint"] = "stale"
    elif tamper == "app":
        report["apps"][0]["bundle_id"] = "other"
    elif tamper == "candidate_binding":
        report["apps"][0]["model_suggestion"]["app_id"] = "a1"
    else:
        report["complete"] = False
    with pytest.raises(ValueError):
        recheck_report(layout, report, config)


def test_cli_recheck_and_conversion_make_no_network_and_keep_originals(tmp_path, monkeypatch):
    layout = Layout.from_raw(
        [[], [folder("Finance", icon("peer", "PayPal")), icon("com.go-jek.gopay", "GoPay")]]
    )
    config = Config()
    report = cloud(layout, config, tmp_path)
    snapshot = tmp_path / "source.json"
    source_plan = tmp_path / "plans/latest.json"
    original_report = tmp_path / "reviews/original.json"
    write_json(snapshot, layout_document(layout))
    write_json(source_plan, build_plan(layout, config).to_dict(config))
    write_json(original_report, report)
    source_bytes, report_bytes = source_plan.read_bytes(), original_report.read_bytes()
    monkeypatch.setattr("socket.socket.connect", lambda *a: pytest.fail("No network"))
    monkeypatch.setattr("sborganize.cli.cloud_provider", lambda *a: pytest.fail("No key prompt"))
    monkeypatch.setattr("sborganize.apple.AppleProvider.probe", lambda *a: pytest.fail("No Apple"))
    prefix = ["--data-dir", str(tmp_path)]
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            *prefix,
            "review",
            "--from-plan",
            str(source_plan),
            "--recheck",
            str(original_report),
            "--no-network",
        ],
    )
    assert result.exit_code == 0, result.exception
    rechecked = read_json(tmp_path / "reviews/rechecked.json")
    assert rechecked["requests"] == 0 and rechecked["rechecked_locally"]
    result = runner.invoke(
        app,
        [
            *prefix,
            "plan",
            "--source-plan",
            str(source_plan),
            "--from-review",
            str(original_report),
            "--device-ready",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert "saved model advice + local rules" in result.stdout
    target = tmp_path / "plans/reorganization.json"
    assert Plan.from_dict(read_json(target)).device_ready
    result = runner.invoke(
        app, [*prefix, "apply", "--fixture", str(snapshot), "--plan", str(target), "--yes"]
    )
    assert result.exit_code == 0, result.exception
    assert "Simulation verified" in result.stdout
    assert source_plan.read_bytes() == source_bytes and original_report.read_bytes() == report_bytes


def test_additive_refresh_preserves_current_payloads_and_classifies_new_apps_locally(tmp_path):
    original = Layout.from_raw(
        [
            [icon("dock")],
            [folder("Finance", icon("peer", "PayPal")), icon("com.go-jek.gopay", "GoPay")],
        ]
    )
    config = Config(folders={"Finance": "Finance"}, categories={"new": "Finance"})
    report = cloud(original, config, tmp_path)
    raw = original.to_raw()
    raw[0][0]["bundleVersion"] = "new-dock-version"
    raw[1][1]["bundleVersion"] = "new-app-version"
    raw[1].append(icon("new", "New app"))
    current = Layout.from_raw(raw)
    plan = prepare_device_plan(refresh_reorganization(original, current, report, config))
    validate_target(current, plan.after)
    assert len(plan.after.apps()) == 4 and plan.after.raw[0] == current.raw[0]
    assert (
        next(a for a in plan.after.apps() if a.bundle_id == "com.go-jek.gopay").raw["bundleVersion"]
        == "new-app-version"
    )
    assert plan.smart_info["model_reviewed_apps"] == 3
    assert plan.smart_info["locally_added_apps"] == 1
    assert len(plan.smart_info["accepted"]) == 2


@pytest.mark.parametrize("mutation", ["reorder", "remove", "folder_insert", "opaque"])
def test_refresh_refuses_existing_structure_changes(tmp_path, mutation):
    original = Layout.from_raw(
        [
            [],
            [
                folder("Finance", icon("peer", "PayPal")),
                icon("one"),
                {"listType": "future", "data": 1},
            ],
        ]
    )
    config = Config()
    report = cloud(original, config, tmp_path)
    raw = original.to_raw()
    if mutation == "reorder":
        raw[1][0], raw[1][1] = raw[1][1], raw[1][0]
    elif mutation == "remove":
        raw[1].pop()
    elif mutation == "folder_insert":
        raw[1][0]["iconLists"][0].append(icon("new"))
    else:
        raw[1][2]["data"] = 2
    with pytest.raises(ValueError, match="changed|removed"):
        refresh_reorganization(original, Layout.from_raw(raw), report, config)


def test_added_regional_service_cannot_fall_back_to_domain_folder(tmp_path):
    original = Layout.from_raw([[], [folder("Finance", icon("peer", "PayPal")), folder("🇨🇳")]])
    config = Config(
        folders={"Finance": "Finance"}, categories={"new": "Finance"}, regions={"new": "CN"}
    )
    report = cloud(original, config, tmp_path)
    current = Layout.from_raw([[], [*original.raw[1], icon("new", "Local service")]])
    plan = refresh_reorganization(original, current, report, config)
    assert plan.after.raw[1][1]["iconLists"][0][0]["bundleIdentifier"] == "new"


def test_unknown_added_app_stays_loose_and_is_not_claimed_as_cloud_reviewed(tmp_path):
    original = Layout.from_raw([[], [folder("Finance", icon("peer", "PayPal"))]])
    config = Config()
    report = cloud(original, config, tmp_path)
    current = Layout.from_raw([[], [*original.raw[1], icon("new", "Unknown")]])
    plan = refresh_reorganization(original, current, report, config)
    assert plan.after.raw == current.raw
    assert plan.smart_info["model_reviewed_apps"] == 1
    assert any(row["bundle_id"] == "new" for row in plan.unresolved)
