import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.config import Config, load_config
from sborganize.guides import GUIDES
from sborganize.planner import Plan, build_plan
from sborganize.policy import build_policy_plan
from sborganize.storage import (
    layout_from_document,
    read_json,
    select_plan,
    selected_plan,
    write_json,
)
from sborganize.terminal import set_plain, write_text

runner = CliRunner()
FIXTURE = Path(__file__).parents[1] / "fixtures/demo_layout.json"


@pytest.fixture
def no_external_io(monkeypatch):
    monkeypatch.setattr("sborganize.cli.connect_usb", lambda *a, **k: pytest.fail("No USB"))
    monkeypatch.setattr("socket.socket.connect", lambda *a, **k: pytest.fail("No network"))
    monkeypatch.setattr("sborganize.apple.AppleProvider.probe", lambda *a: pytest.fail("No Apple"))


def test_welcome_is_successful_clear_and_does_not_create_data(tmp_path, no_external_io):
    root = tmp_path / "new"
    result = runner.invoke(app, ["--data-dir", str(root)])
    assert result.exit_code == 0, result.exception
    assert "sborganize demo" in result.stdout and "sborganize guide" in result.stdout
    assert not root.exists()


def test_demo_runs_outside_checkout_and_does_not_depend_on_personal_preferences(
    tmp_path, monkeypatch, no_external_io
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[planner]\ncreate_folders=false\ncompact_folders=false\n"
    )
    result = runner.invoke(app, ["--data-dir", str(tmp_path), "demo"])
    assert result.exit_code == 0, result.exception
    assert "26 → 81" in result.stdout and "sborganize demo --details" not in result.stdout
    assert "Add --details" in result.stdout and "fixtures/demo_layout.json" not in result.stdout
    assert not (tmp_path / "plans").exists()


def test_saved_demo_show_apply_backups_restore_end_to_end(tmp_path, no_external_io):
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(app, [*prefix, "demo", "--save", "--json"])
    assert result.exit_code == 0, result.exception
    data = json.loads(result.stdout)
    fixture = Path(data["fixture"])
    original = fixture.read_bytes()
    selected = selected_plan(tmp_path)
    assert selected.name == "demo.json"
    for options in [["show"], ["show", "--details"], ["show", "--after"], ["show", "--json"]]:
        shown = runner.invoke(app, [*prefix, *options])
        assert shown.exit_code == 0, shown.exception
    applied = runner.invoke(app, [*prefix, "apply", "--fixture", str(fixture), "--yes"])
    assert applied.exit_code == 0, applied.exception
    for stage in ("1/3", "2/3", "3/3"):
        assert stage in applied.stdout
    listed = runner.invoke(app, [*prefix, "backups", "--json"])
    backups = json.loads(listed.stdout)["backups"]
    assert len(backups) == 1 and backups[0]["source"] == "fixture"
    restored = runner.invoke(
        app, [*prefix, "restore", "--fixture", str(tmp_path / "simulations/latest.json"), "--yes"]
    )
    assert restored.exit_code == 0, restored.exception
    assert layout_from_document(read_json(tmp_path / "simulations/restored.json")).raw == (
        layout_from_document(read_json(fixture)).raw
    )
    assert fixture.read_bytes() == original


def test_apply_selects_newest_mode_instead_of_older_latest_json(tmp_path, layout, no_external_io):
    first = build_plan(layout, Config())
    second = build_plan(layout, Config(create_folders=False, compact_folders=False))
    assert first.after.raw != second.after.raw
    write_json(tmp_path / "plans/latest.json", first.to_dict(Config()))
    alternate = tmp_path / "plans/domain-policy.json"
    write_json(alternate, second.to_dict(Config()))
    select_plan(tmp_path, alternate)
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path), "apply", "--fixture", str(FIXTURE), "--yes"]
    )
    assert result.exit_code == 0, result.exception
    actual = layout_from_document(read_json(tmp_path / "simulations/latest.json"))
    assert actual.raw == second.after.raw
    assert Plan.from_dict(read_json(tmp_path / "plans/latest.json")).after.raw == first.after.raw


@pytest.mark.parametrize(
    "selection", ["../backups/private.json", "/tmp/private.json", "selected.json", None]
)
def test_plan_pointer_cannot_escape_plan_storage(tmp_path, selection):
    write_json(tmp_path / "plans/selected.json", {"schema_version": 1, "plan": selection})
    with pytest.raises(ValueError, match="selection"):
        selected_plan(tmp_path)


def test_config_init_matches_defaults_and_never_overwrites(tmp_path, no_external_io):
    prefix = ["--data-dir", str(tmp_path)]
    first = runner.invoke(app, [*prefix, "config", "init"])
    assert first.exit_code == 0, first.exception
    path = tmp_path / "config.toml"
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_config(path) == Config()
    original = path.read_bytes()
    second = runner.invoke(app, [*prefix, "config", "init"])
    assert second.exit_code == 0 and "already exists" in second.stdout
    assert path.read_bytes() == original
    assert runner.invoke(app, [*prefix, "config", "path"]).stdout.strip() == str(path)


def test_custom_config_can_be_initialized_but_missing_explicit_config_blocks_planning(tmp_path):
    path = tmp_path / "custom/preferences.toml"
    result = runner.invoke(app, ["--config", str(path), "config", "init"])
    assert result.exit_code == 0 and path.exists()
    missing = runner.invoke(app, ["--config", str(tmp_path / "missing.toml"), "demo"])
    assert missing.exit_code == 1


@pytest.mark.parametrize("topic", list(GUIDES))
def test_installed_guides_are_local_and_require_no_credits(
    tmp_path, topic, monkeypatch, no_external_io
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-that-must-not-be-used")
    result = runner.invoke(app, ["--data-dir", str(tmp_path), "guide", topic])
    assert result.exit_code == 0, result.exception
    assert "sborganize" in result.stdout
    assert "secret-that-must-not-be-used" not in result.stdout
    assert not (tmp_path / "plans").exists()


def test_json_and_no_color_work_even_with_forced_terminal_color(tmp_path):
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(app, [*prefix, "demo", "--json"], env={"FORCE_COLOR": "1"}, color=True)
    assert result.exit_code == 0 and json.loads(result.stdout)["plan"]
    assert "\x1b[" not in result.stdout
    for options in [["demo"], ["--help"]]:
        result = runner.invoke(
            app, [*prefix, "--no-color", *options], env={"FORCE_COLOR": "1"}, color=True
        )
        assert result.exit_code == 0, result.exception
        assert "\x1b[" not in result.stdout


def test_terminal_treats_app_labels_as_text_and_removes_escape_controls(capsys):
    set_plain(True)
    write_text("App [red]name[/red] \x1b[31mspoof")
    output = capsys.readouterr().out
    assert "[red]name[/red]" in output and "\x1b" not in output
    set_plain(False)


def test_policy_export_is_complete_editable_and_refuses_overwrite(tmp_path, no_external_io):
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(app, [*prefix, "policy", "export", "--fixture", str(FIXTURE)])
    assert result.exit_code == 0, result.exception
    draft = tmp_path / "policies/draft.json"
    source = tmp_path / "policies/draft.source.json"
    data = read_json(draft)
    layout = layout_from_document(read_json(source))
    assert len(data["apps"]) == len(layout.apps()) == 28
    assert any(a["folder"] == "REVIEW" for a in data["apps"].values())
    assert draft.stat().st_mode & 0o777 == source.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        build_policy_plan(layout, data, Config())
    original = draft.read_bytes()
    again = runner.invoke(app, [*prefix, "policy", "export", "--fixture", str(FIXTURE)])
    assert again.exit_code == 1 and draft.read_bytes() == original
    assert not (tmp_path / "plans").exists()


def test_unreadable_backups_are_reported_instead_of_crashing(tmp_path):
    write_json(tmp_path / "backups/broken.json", {"kind": "backup", "schema_version": 1})
    result = runner.invoke(app, ["--data-dir", str(tmp_path), "backups", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["invalid"]) == 1 and data["backups"] == []
