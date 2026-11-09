"""Install a wheel in a clean environment and exercise the offline user workflow."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    wheel = parser.parse_args().wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("Pass an existing wheel file.")
    with tempfile.TemporaryDirectory(prefix="sborganize-wheel-") as temporary:
        work = Path(temporary)
        environment = work / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], check=True)
        env = dict(os.environ, NO_COLOR="1")
        env.pop("PYTHONPATH", None)
        env.pop("OPENROUTER_API_KEY", None)
        root = work / "data"
        prefix = [str(python), "-m", "sborganize", "--data-dir", str(root)]

        def run(*args):
            result = subprocess.run(
                [*prefix, *args], cwd=work, env=env, text=True, capture_output=True, check=True
            )
            return result.stdout

        assert "sborganize demo" in run()
        assert "26 → 81" in run("demo")
        assert not root.exists()
        for topic in ("start", "offline", "config", "policy", "cloud", "safety"):
            assert "sborganize" in run("guide", topic)
        run("config", "init")
        assert (root / "config.toml").is_file()
        data = json.loads(run("demo", "--save", "--json"))
        fixture = data["fixture"]
        assert json.loads(run("show", "--json"))["source"] == "fixture"
        assert "3 pages" in run("show", "--after")
        assert "Simulation verified" in run("apply", "--fixture", fixture, "--yes")
        assert len(json.loads(run("backups", "--json"))["backups"]) == 1
        assert "Restore simulation verified" in run(
            "restore", "--fixture", str(root / "simulations/latest.json"), "--yes"
        )
        run("policy", "export", "--fixture", fixture)
        assert (root / "policies/draft.source.json").is_file()
        print(
            "Installed-wheel smoke passed: bundled guides/config, demo, plan selection, "
            "show, fixture apply/restore, backups and policy export. No phone or model used."
        )


if __name__ == "__main__":
    main()
