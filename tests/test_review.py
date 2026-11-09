import json
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.config import Config
from sborganize.model import Layout
from sborganize.openrouter import OpenRouterProvider, OpenRouterUnavailable
from sborganize.planner import Plan
from sborganize.review import BATCH_SIZE, inventory, normalize_batch, render_review, review_layout
from sborganize.storage import read_json


def icon(bundle, name):
    return {"bundleIdentifier": bundle, "displayName": name}


def folder(name, *children):
    return {"displayName": name, "iconLists": [list(children)]}


def result(app_id, **overrides):
    return {
        "app_id": app_id,
        "purpose_known": True,
        "domain": "Finance",
        "region": "GLOBAL",
        "confidence": "high",
        "target": "keep",
        "reason": "Current grouping suits this app.",
        **overrides,
    }


class FakeProvider:
    def __init__(self, decide=None, fail_on=None):
        self.requests = []
        self.decide = decide or (lambda row, folders: {})
        self.fail_on = fail_on

    def review_batch(self, request):
        self.requests.append(request)
        if len(self.requests) == self.fail_on:
            raise OpenRouterUnavailable("Synthetic provider failure.")
        data = json.loads(request["prompt"])
        return {
            "placements": [
                result(row["app_id"], **self.decide(row, data["folders"])) for row in data["apps"]
            ]
        }


def test_whole_review_includes_grouped_dock_pins_and_unknowns_without_mutation(tmp_path):
    layout = Layout.from_raw(
        [
            [icon("dock", "Phone")],
            [
                folder("Finance", icon("wrong", "Maps"), icon("pin", "Pinned")),
                folder("Travel", icon("peer", "Uber")),
                icon("loose", "Mystery"),
                {"listType": "widget", "private": "widget-secret"},
            ],
        ],
        "private-device-id",
    )
    original = deepcopy(layout.raw)

    def decide(row, folders):
        target = next(f["id"] for f in folders if f["name"] == "Travel")
        return {"target": target, "domain": "Transport"} if row["bundle_id"] == "wrong" else {}

    provider = FakeProvider(decide)
    report = review_layout(
        layout, Config(pins=("pin",)), tmp_path, cloud=True, provider_factory=lambda: provider
    )
    assert report["complete"] and report["counts"]["reviewed"] == len(layout.apps()) == 5
    assert report["counts"]["protected"] == 3  # Dock and every child of the pinned folder.
    wrong = next(r for r in report["apps"] if r["bundle_id"] == "wrong")
    assert wrong["status"] == "protected" and wrong["advice_status"] == "move"
    assert layout.raw == original
    assert not (tmp_path / "plans").exists()
    serialized = json.dumps([provider.requests, report])
    for secret in ("private-device-id", "widget-secret", "iconLists", "source_state_plist"):
        assert secret not in serialized
    with pytest.raises(ValueError, match="advisory"):
        Plan.from_dict(report)


def test_grouped_apps_can_move_and_current_region_is_not_authoritative(tmp_path):
    layout = Layout.from_raw(
        [
            [],
            [
                folder("🇨🇳", icon("global-tool", "Tool")),
                folder("HK"),
                folder("Finance", icon("cn-local", "Local")),
            ],
        ]
    )

    def decide(row, folders):
        assert row["region_hint"] is None if row["bundle_id"] == "global-tool" else True
        region = "GLOBAL" if row["bundle_id"] == "global-tool" else "CN"
        name = "Finance" if region == "GLOBAL" else "🇨🇳"
        return {"region": region, "target": next(f["id"] for f in folders if f["name"] == name)}

    report = review_layout(
        layout,
        Config(regions={"cn-local": "CN"}),
        tmp_path,
        cloud=True,
        provider_factory=lambda: FakeProvider(decide),
    )
    assert report["counts"]["move"] == 2
    assert all(
        len(f["incoming"]) == len(f["outgoing"]) == 1
        for f in report["folders"]
        if f["name"] != "HK"
    )


@pytest.mark.parametrize(
    "suggested",
    [
        {"region": "HK", "target": "f0"},  # Wrong regional folder for known CN service.
        {"region": "GLOBAL"},  # Keep cannot bypass authoritative region.
        {"purpose_known": False},
        {"confidence": "medium"},
        {"region": "unknown"},
    ],
)
def test_uncertainty_or_region_conflict_requires_review(tmp_path, suggested):
    layout = Layout.from_raw([[], [folder("HK", icon("app", "Known")), folder("🇨🇳")]])
    report = review_layout(
        layout,
        Config(regions={"app": "CN"}),
        tmp_path,
        cloud=True,
        provider_factory=lambda: FakeProvider(lambda r, f: suggested),
    )
    assert report["complete"] and report["counts"]["review"] == 1
    assert report["counts"]["move"] == report["counts"]["keep"] == 0


def test_keep_cannot_bypass_explicit_category_target(tmp_path):
    layout = Layout.from_raw([[], [folder("Utilities", icon("app", "Tool")), folder("Finance")]])
    config = Config(categories={"app": "Finance"}, folders={"Finance": "Finance"})
    report = review_layout(
        layout, config, tmp_path, cloud=True, provider_factory=lambda: FakeProvider()
    )
    assert report["counts"]["review"] == 1


def test_partial_failure_resumes_cache_without_repeating_successful_batches(tmp_path):
    layout = Layout.from_raw(
        [[], [folder("Finance", *[icon(f"app{i:03}", "App") for i in range(BATCH_SIZE * 2 + 1)])]]
    )
    first = FakeProvider(fail_on=2)
    report = review_layout(layout, Config(), tmp_path, cloud=True, provider_factory=lambda: first)
    assert not report["complete"] and report["counts"]["reviewed"] == BATCH_SIZE
    assert report["counts"]["unreviewed"] == BATCH_SIZE + 1
    assert len(first.requests) == 2  # No retries.
    second = FakeProvider()
    report = review_layout(layout, Config(), tmp_path, cloud=True, provider_factory=lambda: second)
    assert report["complete"] and len(second.requests) == 2
    assert report["cached_batches"] == 1
    report = review_layout(
        layout,
        Config(),
        tmp_path,
        cloud=True,
        provider_factory=lambda: pytest.fail("No key or provider needed"),
    )
    assert report["requests"] == 0 and report["cached_batches"] == 3
    refreshed = FakeProvider()
    report = review_layout(
        layout, Config(), tmp_path, cloud=True, refresh=True, provider_factory=lambda: refreshed
    )
    assert report["requests"] == len(refreshed.requests) == 3
    for path in (tmp_path / "cache/reviews").glob("*.json"):
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("malformed", ["duplicate", "missing", "wrong_target", "bad_type"])
def test_invalid_batch_is_unreviewed_and_never_cached(tmp_path, malformed):
    layout = Layout.from_raw([[], [icon("a", "A"), icon("b", "B")]])

    class Invalid(FakeProvider):
        def review_batch(self, request):
            response = super().review_batch(request)
            rows = response["placements"]
            if malformed == "duplicate":
                rows[1]["app_id"] = rows[0]["app_id"]
            elif malformed == "missing":
                rows.pop()
            elif malformed == "wrong_target":
                rows[0]["target"] = "New made-up folder"
            else:
                rows[0]["purpose_known"] = "yes"
            return response

    report = review_layout(
        layout, Config(), tmp_path, cloud=True, provider_factory=lambda: Invalid()
    )
    assert not report["complete"] and report["counts"]["unreviewed"] == 2
    assert not list((tmp_path / "cache").rglob("*.json"))
    assert report["batch_diagnostics"][0]["issues"]
    diagnostic_path = next((tmp_path / "reviews/rejected").glob("*.json"))
    assert diagnostic_path.stat().st_mode & 0o777 == 0o600
    assert "unreviewed A" not in render_review(report)
    assert "Unreviewed 2" in render_review(report)


def test_cloud_inventory_limit_precedes_provider_acquisition(tmp_path):
    layout = Layout.from_raw([[], [icon(f"id{i}", "App") for i in range(513)]])
    with pytest.raises(ValueError, match="512"):
        review_layout(
            layout,
            Config(),
            tmp_path,
            cloud=True,
            provider_factory=lambda: pytest.fail("No prompt or network"),
        )


def test_nested_and_opaque_folders_are_protected_but_apps_included(tmp_path):
    layout = Layout.from_raw(
        [
            [],
            [
                folder("Mixed", icon("one", "App"), {"listType": "future", "data": b"secret"}),
                folder("Outer", folder("Inner", icon("nested", "Nested"))),
            ],
        ]
    )
    records, _, _ = inventory(layout, Config())
    assert len(records) == 2 and all(r["protected"] for r in records)
    assert (
        next(r for r in records if r["bundle_id"] == "nested")["current_label"] == "Outer / Inner"
    )


def test_rules_reviews_already_grouped_apps_offline(tmp_path, monkeypatch):
    monkeypatch.setattr("socket.socket.connect", lambda *a: pytest.fail("No network"))
    layout = Layout.from_raw(
        [[], [folder("Utilities", icon("notion", "Notion")), folder("Productivity")]]
    )
    report = review_layout(layout, Config(), tmp_path)
    assert report["counts"]["move"] == 1 and report["complete"]


def test_review_cli_saved_snapshot_preserves_plan_and_reports_partial_failure(
    tmp_path, monkeypatch
):
    fixture = Path(__file__).parents[1] / "fixtures/demo_layout.json"
    runner = CliRunner()
    prefix = ["--data-dir", str(tmp_path)]
    assert runner.invoke(app, [*prefix, "plan", "--fixture", str(fixture)]).exit_code == 0
    path = tmp_path / "plans/latest.json"
    original = path.read_bytes()
    monkeypatch.setattr("sborganize.cli.read_layout", lambda *a: pytest.fail("No USB read"))
    monkeypatch.setattr("sborganize.apple.AppleProvider.probe", lambda *a: pytest.fail("No Apple"))
    args = [*prefix, "review", "--from-plan", str(path), "--json"]
    local = runner.invoke(app, args)
    assert local.exit_code == 0, local.exception
    assert json.loads(local.stdout)["counts"]["total"] == 28
    monkeypatch.setattr("sborganize.cli.cloud_provider", lambda c: FakeProvider(fail_on=2))
    cloud = runner.invoke(app, [*args, "--cloud"])
    assert cloud.exit_code == 1
    assert not json.loads(cloud.stdout)["complete"]
    assert "ALL Home Screen" in cloud.stderr
    assert path.read_bytes() == original
    assert read_json(tmp_path / "reviews/latest.json")["counts"]["reviewed"] == BATCH_SIZE
    with pytest.raises(ValueError, match="advisory"):
        Plan.from_dict(read_json(tmp_path / "reviews/latest.json"))


def test_no_network_rejects_before_read_or_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr("sborganize.cli.read_layout", lambda *a: pytest.fail("No read"))
    monkeypatch.setattr("sborganize.cli.cloud_provider", lambda *a: pytest.fail("No prompt"))
    run = CliRunner().invoke(app, ["review", "--cloud", "--no-network"])
    assert run.exit_code == 1


def test_openrouter_batch_schema_is_bounded_and_covers_every_id(monkeypatch):
    captured = {}

    def generate(self, request, schema, max_tokens):
        captured.update(schema=schema, max_tokens=max_tokens)
        return {"placements": []}

    monkeypatch.setattr(OpenRouterProvider, "_generate", generate)
    OpenRouterProvider(api_key="synthetic-key").review_batch(
        {"app_ids": ["a0", "a1"], "targets": ["keep", "f0"]}
    )
    mapping = captured["schema"]["properties"]["placements"]
    assert mapping["type"] == "object" and mapping["required"] == ["a0", "a1"]
    assert mapping["additionalProperties"] is False
    for item in mapping["properties"].values():
        assert item["properties"]["domain"]["minLength"] == 1
        assert item["properties"]["reason"]["minLength"] == 1
        assert "app_id" not in item["properties"]
    assert captured["max_tokens"] == 4096


def test_keyed_batch_normalization_retains_binding_and_does_not_coerce_types():
    response = {"placements": {"a0": {k: v for k, v in result("a0").items() if k != "app_id"}}}
    normalized = normalize_batch(response)
    assert normalized == {"placements": [result("a0")]}
    response["placements"]["a0"]["app_id"] = "a1"
    assert normalize_batch(response) == response  # Conflicting IDs must not be masked.


def test_keyed_http_response_drives_complete_review_and_cache(tmp_path, monkeypatch):
    layout = Layout.from_raw([[], [folder("Finance", icon("app", "Bank"))]])
    sent = []

    class Response:
        status = 200

        def read(self, limit):
            payload = {
                "placements": {"a0": {k: v for k, v in result("a0").items() if k != "app_id"}}
            }
            return json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(payload)}}
                    ]
                }
            ).encode()

    class Connection:
        def __init__(self, host, timeout):
            assert host == "openrouter.ai"

        def request(self, method, path, body, headers):
            sent.append(json.loads(body))
            assert headers["Authorization"] == "Bearer test-key"

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("sborganize.openrouter.http.client.HTTPSConnection", Connection)
    report = review_layout(
        layout,
        Config(),
        tmp_path,
        cloud=True,
        provider_factory=lambda: OpenRouterProvider(api_key="test-key"),
    )
    assert report["complete"] and report["counts"]["keep"] == 1
    assert "test-key" not in json.dumps(report) + json.dumps(sent)
    assert sent[0]["response_format"]["json_schema"]["schema"]["properties"]["placements"][
        "required"
    ] == ["a0"]


def test_empty_unknown_fields_are_diagnosed_by_name(tmp_path):
    layout = Layout.from_raw([[], [icon("app", "Unknown")]])
    report = review_layout(
        layout,
        Config(),
        tmp_path,
        cloud=True,
        provider_factory=lambda: FakeProvider(
            lambda r, f: {"purpose_known": False, "domain": "", "reason": ""}
        ),
    )
    assert not report["complete"]
    issues = report["batch_diagnostics"][0]["issues"]
    assert {issue["field"] for issue in issues} == {"domain", "reason"}
    assert "domain" in report["errors"][0]


def test_duplicate_json_keys_are_rejected_before_normalization():
    from sborganize.openrouter import unique_object

    with pytest.raises(OpenRouterUnavailable, match="duplicate object keys"):
        json.loads('{"placements":{"a0":{},"a0":{}}}', object_pairs_hook=unique_object)


@pytest.mark.parametrize("content", [None, {"placements": {}}, ["not text"]])
def test_nontext_provider_content_is_a_concise_failure(monkeypatch, content):
    class Connection:
        def __init__(self, *a, **k):
            self.status = 200

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return self

        def read(self, limit):
            return json.dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
            ).encode()

        def close(self):
            pass

    monkeypatch.setattr("sborganize.openrouter.http.client.HTTPSConnection", Connection)
    with pytest.raises(OpenRouterUnavailable, match="no JSON message content"):
        OpenRouterProvider(api_key="test-key").classify(
            {"targets": ["keep"], "instructions": "Classify", "prompt": "App"}
        )
