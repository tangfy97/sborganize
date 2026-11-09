import json
from dataclasses import replace

import pytest

from sborganize.apple import AppleProvider, AppleUnavailable
from sborganize.config import Config
from sborganize.model import Layout, validate_target
from sborganize.openrouter import OpenRouterProvider, OpenRouterUnavailable
from sborganize.planner import Plan, build_plan
from sborganize.smart import refine_plan


class FakeApple:
    def __init__(self, result=None, available=True):
        self.result, self.available, self.requests = result, available, []

    def probe(self):
        return {"available": self.available, "detail": "Test model"}

    def classify(self, request):
        self.requests.append(request)
        return self.result


@pytest.fixture
def smart_case():
    layout = Layout.from_raw(
        [
            [],
            [
                {
                    "displayName": "Work",
                    "iconLists": [[{"bundleIdentifier": "peer", "displayName": "Notes"}]],
                },
                {"displayName": "🇨🇳", "iconLists": [[]]},
                {"bundleIdentifier": "com.example.unknown", "displayName": "Uncatalogued"},
                {"listType": "widget", "secret": "raw-opaque-data"},
            ],
        ],
        udid="private-device-id",
    )
    config = Config(create_folders=False, compact_folders=False)
    return layout, config, build_plan(layout, config)


def suggestion(**overrides):
    return {
        "purpose_known": True,
        "domain": "Productivity",
        "region": "GLOBAL",
        "confidence": "high",
        "target": "folder:1:0",
        "reason": "Clear productivity tool.",
        **overrides,
    }


def test_unavailable_keeps_rules_without_inference(smart_case, tmp_path):
    _, config, baseline = smart_case
    provider = FakeApple(available=False)
    refined = refine_plan(baseline, config, tmp_path, provider=provider)
    assert refined.after.raw == baseline.after.raw and refined.provider == "rules"
    assert not provider.requests


def test_valid_suggestion_preserves_payloads_and_round_trips(smart_case, tmp_path):
    layout, config, baseline = smart_case
    refined = refine_plan(baseline, config, tmp_path, provider=FakeApple(suggestion()))
    assert refined.after.raw[1][0]["iconLists"][0][-1] == layout.raw[1][2]
    assert refined.after.raw[1][3] == layout.raw[1][3]
    validate_target(layout, refined.after)
    assert refined.provider == "rules+apple-on-device"
    loaded = Plan.from_dict(refined.to_dict(config))
    assert loaded.provider == refined.provider and loaded.smart_info == refined.smart_info


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        suggestion(target=[]),
        suggestion(target="invented"),
        suggestion(purpose_known=False),
        suggestion(confidence="medium"),
        suggestion(target="keep"),
        suggestion(region="unknown"),
        suggestion(region="CN"),
        suggestion(domain="unknown"),
    ],
)
def test_invalid_or_uncertain_models_never_change_layout(smart_case, tmp_path, result):
    _, config, baseline = smart_case
    refined = refine_plan(baseline, config, tmp_path, provider=FakeApple(result))
    assert refined.after.raw == baseline.after.raw and refined.unresolved == baseline.unresolved


def test_verbose_reason_does_not_discard_valid_destination(smart_case, tmp_path):
    _, config, baseline = smart_case
    refined = refine_plan(
        baseline, config, tmp_path, provider=FakeApple(suggestion(reason="x" * 600))
    )
    assert len(refined.smart_info["accepted"]) == 1
    assert len(refined.smart_info["accepted"][0]["reason"]) == 300


def test_rejected_candidate_has_field_specific_diagnostics(smart_case, tmp_path):
    _, config, baseline = smart_case
    refined = refine_plan(
        baseline,
        config,
        tmp_path,
        provider=FakeApple(suggestion(target="folder-name-instead-of-id")),
    )
    review = refined.smart_info["review"][0]
    assert "folder ID" in review["reason"]
    assert review["candidate"]["target"] == "folder-name-instead-of-id"


def test_pins_and_explicit_categories_remain_authoritative(smart_case, tmp_path):
    layout, config, baseline = smart_case
    provider = FakeApple(suggestion())
    refined = refine_plan(
        baseline, replace(config, pins=("com.example.unknown",)), tmp_path, provider=provider
    )
    assert not provider.requests and refined.after.raw == baseline.after.raw
    configured = replace(config, categories={"com.example.unknown": "Personal"})
    refined = refine_plan(
        build_plan(layout, configured), configured, tmp_path, provider=FakeApple(suggestion())
    )
    assert refined.after.raw == layout.raw


def test_minimal_prompts_do_not_contain_raw_state_identity_or_known_cloud_peers(
    smart_case, tmp_path
):
    _, config, baseline = smart_case
    for cloud in (True, False):
        provider = FakeApple(suggestion())
        refine_plan(baseline, config, tmp_path, provider=provider, cloud=cloud)
        payload = json.dumps(provider.requests)
        assert "private-device-id" not in payload and "raw-opaque-data" not in payload
        assert "source_state_plist" not in payload and "iconLists" not in payload
        assert "Uncatalogued" in payload
        if cloud:
            assert "Notes" not in payload and "domains" in payload


def test_local_mode_never_constructs_cloud_provider_even_with_key(
    smart_case, tmp_path, monkeypatch
):
    _, config, baseline = smart_case
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-not-for-logs")
    monkeypatch.setattr("sborganize.smart.AppleProvider", lambda root: FakeApple(available=False))
    monkeypatch.setattr(
        "sborganize.smart.OpenRouterProvider", lambda model: pytest.fail("Cloud forbidden")
    )
    assert refine_plan(baseline, config, tmp_path).provider == "rules"


def test_apple_platform_gate_needs_no_compiler_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr("sborganize.apple.platform.system", lambda: "Linux")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No subprocess expected"))
    assert not AppleProvider(tmp_path).probe()["available"]


def test_generation_failure_keeps_rules_with_explicit_notice(smart_case, tmp_path):
    _, config, baseline = smart_case

    class Failed(FakeApple):
        def classify(self, request):
            raise AppleUnavailable("Model assets unavailable.")

    refined = refine_plan(baseline, config, tmp_path, provider=Failed())
    assert refined.after.raw == baseline.after.raw and refined.smart_info["generation_error"]


def test_openrouter_key_stays_out_of_payload_and_plan(smart_case, tmp_path, monkeypatch):
    _, config, baseline = smart_case
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-not-for-logs")
    sent = {}

    class Response:
        status = 200

        def read(self, limit):
            return json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(suggestion())}}
                    ]
                }
            ).encode()

    class Connection:
        def __init__(self, host, timeout):
            assert host == "openrouter.ai"

        def request(self, method, path, body, headers):
            sent.update(json.loads(body))
            assert path == "/api/v1/chat/completions"
            assert headers["Authorization"] == "Bearer secret-not-for-logs"

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("sborganize.openrouter.http.client.HTTPSConnection", Connection)
    refined = refine_plan(baseline, config, tmp_path, cloud=True, provider=OpenRouterProvider())
    assert "secret-not-for-logs" not in json.dumps(sent)
    assert "secret-not-for-logs" not in json.dumps(refined.to_dict(config))
    assert sent["provider"]["allow_fallbacks"] is False
    assert sent["provider"]["data_collection"] == "deny"
    assert sent["max_tokens"] == 256 and sent["model"] == "qwen/qwen3.5-flash-02-23"


def test_missing_cloud_key_makes_no_connection(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        "sborganize.openrouter.http.client.HTTPSConnection",
        lambda *a, **k: pytest.fail("No network allowed"),
    )
    provider = OpenRouterProvider()
    assert not provider.probe()["available"]
    with pytest.raises(OpenRouterUnavailable):
        provider.classify({})


def test_hidden_terminal_key_is_ephemeral_and_not_echoed(monkeypatch, capsys):
    from sborganize.cli import cloud_provider

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt: "ephemeral-secret-value")
    provider = cloud_provider(Config())
    assert provider.probe()["available"]
    assert "ephemeral-secret-value" not in json.dumps(provider.probe())
    assert "ephemeral-secret-value" not in capsys.readouterr().out
    import os

    assert "OPENROUTER_API_KEY" not in os.environ


def test_hidden_input_never_falls_back_to_echo(monkeypatch):
    import getpass
    import warnings

    from sborganize.cli import cloud_provider

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def cannot_hide(prompt):
        warnings.warn("Cannot hide input", getpass.GetPassWarning, stacklevel=1)
        pytest.fail("Must not continue to echoed input")

    monkeypatch.setattr("getpass.getpass", cannot_hide)
    with pytest.raises(ValueError, match="Hidden key input unavailable"):
        cloud_provider(Config())
