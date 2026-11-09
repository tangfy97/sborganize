import json
import os
import tempfile
from pathlib import Path

from sborganize.model import Layout, decode_state, encode_state


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


PLAN_NAMES = frozenset({"latest.json", "reorganization.json", "domain-policy.json", "demo.json"})


def select_plan(root: Path, path: Path) -> None:
    if path.parent != root / "plans" or path.name not in PLAN_NAMES:
        raise ValueError("Selected plans must be saved in the plans directory.")
    write_json(root / "plans/selected.json", {"schema_version": 1, "plan": path.name})


def selected_plan(root: Path) -> Path:
    pointer = root / "plans/selected.json"
    if pointer.is_file():
        data = read_json(pointer)
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != 1
            or not isinstance(data.get("plan"), str)
            or data["plan"] not in PLAN_NAMES
        ):
            raise ValueError("Invalid saved-plan selection. Run sborganize plan again.")
        path = root / "plans" / data["plan"]
    else:
        path = root / "plans/latest.json"
    if not path.is_file():
        raise ValueError("No saved plan. Run sborganize plan, or sborganize demo --save.")
    return path


def ensure_private_dir(path: Path) -> None:
    missing = []
    directory = path
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True, mode=0o700)


def write_json(path: Path, data: dict) -> None:
    ensure_private_dir(path.parent)
    descriptor, name = tempfile.mkstemp(prefix=".sborganize-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def layout_document(layout: Layout) -> dict:
    return {
        "schema_version": 1,
        "udid": layout.udid,
        "source": layout.source,
        "icon_state_plist": encode_state(layout.raw),
    }


def layout_from_document(data, *, fixture: bool = True) -> Layout:
    if isinstance(data, list):
        return Layout.from_raw(data)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Expected an IconState list or a schema_version=1 layout document.")
    udid = data.get("udid", "fixture")
    if not isinstance(udid, str) or not udid:
        raise ValueError("Layout UDID must be a nonempty string.")
    raw = (
        decode_state(data["icon_state_plist"]) if "icon_state_plist" in data else data["icon_state"]
    )
    return Layout.from_raw(raw, udid, "fixture" if fixture else data.get("source", "fixture"))
