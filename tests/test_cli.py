import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sborganize.cli import app
from sborganize.storage import layout_from_document, read_json

runner = CliRunner()
FIXTURE = Path(__file__).parents[1] / "fixtures/demo_layout.json"


def test_demo_no_hardware_or_disk_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sborganize.cli.connect_usb",
        lambda _: (_ for _ in ()).throw(AssertionError("No USB allowed")),
    )
    root = tmp_path / "data"
    result = runner.invoke(app, ["--data-dir", str(root), "demo"])
    assert result.exit_code == 0, result.output
    assert "offline demo" in result.output
    assert "26 → 81" in result.output
    assert not root.exists()


def test_json_scan_score_plan_doctor(tmp_path):
    for command in ["scan", "score", "plan", "doctor"]:
        result = runner.invoke(
            app, ["--data-dir", str(tmp_path), command, "--fixture", str(FIXTURE), "--json"]
        )
        assert result.exit_code == 0, (result.output, result.exception)
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
    assert (tmp_path / "plans/latest.json").exists()


def test_full_fixture_apply_restore_flow(tmp_path):
    prefix = ["--data-dir", str(tmp_path)]
    result = runner.invoke(app, [*prefix, "plan", "--fixture", str(FIXTURE)])
    assert result.exit_code == 0, result.exception
    original = FIXTURE.read_bytes()
    result = runner.invoke(app, [*prefix, "apply", "--fixture", str(FIXTURE), "--yes"])
    assert result.exit_code == 0, result.exception
    assert "Simulation verified" in result.output
    simulated = tmp_path / "simulations/latest.json"
    assert len(layout_from_document(read_json(simulated)).pages) == 3
    assert FIXTURE.read_bytes() == original
    result = runner.invoke(app, [*prefix, "restore", "--fixture", str(simulated), "--yes"])
    assert result.exit_code == 0, result.exception
    restored = tmp_path / "simulations/restored.json"
    assert (
        layout_from_document(read_json(restored)).raw
        == layout_from_document(read_json(FIXTURE)).raw
    )
    assert len(list((tmp_path / "backups").glob("*.json"))) == 2


def test_apply_rejects_same_source_output(tmp_path):
    prefix = ["--data-dir", str(tmp_path)]
    runner.invoke(app, [*prefix, "plan", "--fixture", str(FIXTURE)])
    result = runner.invoke(
        app, [*prefix, "apply", "--fixture", str(FIXTURE), "--output", str(FIXTURE), "--yes"]
    )
    assert result.exit_code == 1
    assert not (tmp_path / "backups").exists()


def test_simulation_cannot_overwrite_backup_or_plan(tmp_path):
    prefix = ["--data-dir", str(tmp_path)]
    runner.invoke(app, [*prefix, "plan", "--fixture", str(FIXTURE)])
    runner.invoke(app, [*prefix, "backup", "--fixture", str(FIXTURE)])
    path = next((tmp_path / "backups").glob("*.json"))
    original = path.read_bytes()
    result = runner.invoke(
        app, [*prefix, "apply", "--fixture", str(FIXTURE), "--output", str(path), "--yes"]
    )
    assert result.exit_code == 1
    assert path.read_bytes() == original


def test_smart_falls_back_explicitly_without_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr(
        "sborganize.apple.AppleProvider.probe",
        lambda self: {
            "available": False,
            "detail": "Apple model not ready.",
            "reason": "model_not_ready",
        },
    )
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "plan",
            "--fixture",
            str(FIXTURE),
            "--smart",
            "--no-network",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.exception
    data = json.loads(result.stdout)
    assert data["provider"] == "rules"
    assert "Apple model not ready" in data["notice"]


def test_entrypoint_errors_are_concise_and_live_apply_never_connects(tmp_path):
    for args, message in [
        (["apply", "--yes"], "Phone writes are disabled"),
        (["restore", "--yes"], "Phone writes are disabled"),
        (["scan", "--fixture", str(tmp_path / "missing.json")], "Error:"),
    ]:
        result = subprocess.run(
            [sys.executable, "-m", "sborganize", *args], capture_output=True, text=True
        )
        assert result.returncode == 1
        assert message in result.stderr
        assert "Traceback" not in result.stderr


def test_existing_only_emoji_plan_and_review_output(tmp_path):
    fixture = FIXTURE.with_name("emoji_folders.json")
    args = ["--data-dir", str(tmp_path), "plan", "--fixture", str(fixture), "--existing-only"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.exception
    assert "Loose apps 8 → 2" in result.stdout
    assert "category unknown" in result.stdout
    assert "multiple matching folders · 🚌🚄, ✈️" in result.stdout
    data = json.loads(runner.invoke(app, [*args, "--json"]).stdout)
    assert data["policy"] == {"create_folders": False, "compact_folders": False}
    assert len(data["unresolved"]) == 2
    assert data["score_before"]["scope"] == "grouping"
    result = runner.invoke(app, ["score", "--fixture", str(fixture), "--existing-only", "--json"])
    assert json.loads(result.stdout)["scope"] == "grouping"
    result = runner.invoke(
        app, ["--data-dir", str(tmp_path), "apply", "--fixture", str(fixture), "--yes"]
    )
    assert result.exit_code == 0, result.exception
    assert "Grouping " in result.stdout


def test_cloud_requires_explicit_network_and_cannot_mix_with_smart(tmp_path, monkeypatch):
    monkeypatch.setattr("sborganize.cli.read_layout", lambda *a: pytest.fail("No read expected"))
    for options in [["--smart", "--cloud"], ["--cloud", "--no-network"]]:
        result = runner.invoke(app, ["--data-dir", str(tmp_path), "plan", *options])
        assert result.exit_code == 1
