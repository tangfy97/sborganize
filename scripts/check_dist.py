"""Reject private/runtime content in distributions and create release checksums."""

import hashlib
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN = {".prototype", ".venv", "__pycache__", ".git", "tmp-dumps"}


def check_names(names):
    for name in names:
        parts = Path(name).parts
        if FORBIDDEN.intersection(parts) or any(part.startswith(".env") for part in parts):
            raise SystemExit(f"Private/runtime content in distribution: {name}")


def main():
    from tomllib import loads

    version = loads(Path("pyproject.toml").read_text("utf-8"))["project"]["version"]
    artifacts = [
        Path("dist") / f"sborganize-{version}{suffix}"
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    ]
    with zipfile.ZipFile(artifacts[0]) as wheel:
        check_names(wheel.namelist())
        assert "sborganize/data/default_config.toml" in wheel.namelist()
        assert "sborganize/guides.py" in wheel.namelist()
    with tarfile.open(artifacts[1]) as source:
        check_names(source.getnames())
    hashes = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts]
    Path("dist/SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    print("Distribution names checked; private runtime data excluded. SHA256SUMS written.")


if __name__ == "__main__":
    main()
