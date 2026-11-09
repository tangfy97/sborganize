"""Conservative IconState model; raw payloads remain authoritative."""

from __future__ import annotations

import base64
import hashlib
import plistlib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


def fingerprint(raw: list) -> str:
    return hashlib.sha256(plistlib.dumps(raw, fmt=plistlib.FMT_BINARY, sort_keys=True)).hexdigest()


def structural_fingerprint(raw: list) -> str:
    """Ignore only documented app bookkeeping during post-write verification."""

    def normalize(value):
        node = parse_slot(value)
        if isinstance(node, Icon):
            return {k: v for k, v in value.items() if k not in ("iconModDate", "bundleVersion")}
        if isinstance(node, Folder):
            result = deepcopy(value)
            result["iconLists"] = [
                [normalize(child) for child in page] for page in value["iconLists"]
            ]
            return result
        return deepcopy(value)

    return fingerprint([[normalize(slot) for slot in page] for page in raw])


def encode_state(raw: list) -> str:
    return base64.b64encode(plistlib.dumps(raw, fmt=plistlib.FMT_BINARY)).decode("ascii")


def decode_state(encoded: str) -> list:
    try:
        return plistlib.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError, plistlib.InvalidFileException) as exc:
        raise ValueError("Invalid encoded IconState.") from exc


@dataclass(frozen=True)
class Icon:
    bundle_id: str
    name: str
    raw: dict


@dataclass(frozen=True)
class Folder:
    name: str
    pages: tuple[tuple[Slot, ...], ...]
    raw: dict


@dataclass(frozen=True)
class Opaque:
    raw: Any


@dataclass(frozen=True)
class Empty:
    raw: Any


Slot = Icon | Folder | Opaque | Empty


def parse_slot(raw: Any) -> Slot:
    if raw is None or raw is False or (type(raw) is int and raw == 0):
        return Empty(raw)
    if not isinstance(raw, dict):
        return Opaque(raw)
    # An unfamiliar typed node may carry a bundle ID (widgets do too).
    kinds = (raw.get("listType"), raw.get("iconType"))
    if any(key.casefold().startswith("widget") for key in raw):
        return Opaque(raw)
    if "iconLists" in raw:
        pages = raw["iconLists"]
        if any(kind not in (None, "folder") for kind in kinds) or not isinstance(
            raw.get("displayName"), str
        ):
            return Opaque(raw)
        if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
            return Opaque(raw)
        return Folder(raw["displayName"], tuple(tuple(map(parse_slot, p)) for p in pages), raw)
    if any(kind not in (None, "icon", "application") for kind in kinds):
        return Opaque(raw)
    bundle_id = raw.get("bundleIdentifier") or raw.get("displayIdentifier")
    if isinstance(bundle_id, str) and bundle_id:
        return Icon(bundle_id, str(raw.get("displayName") or bundle_id), raw)
    return Opaque(raw)


@dataclass(frozen=True)
class Page:
    index: int
    slots: tuple[Slot, ...]


@dataclass(frozen=True)
class Layout:
    raw: list
    udid: str
    source: str = "fixture"

    @classmethod
    def from_raw(cls, raw: list, udid: str = "fixture", source: str = "fixture") -> Layout:
        if not isinstance(udid, str) or not udid or source not in ("fixture", "usb"):
            raise ValueError("Layout needs a nonempty device ID and a fixture or usb source.")
        if not isinstance(raw, list) or not raw or not all(isinstance(p, list) for p in raw):
            raise ValueError("IconState must be [dock, page1, ...], with every page a list.")
        fingerprint(raw)  # Refuse payloads that cannot be losslessly encoded as a plist.
        return cls(deepcopy(raw), udid, source)

    @property
    def dock(self) -> tuple[Slot, ...]:
        return tuple(map(parse_slot, self.raw[0]))

    @property
    def pages(self) -> tuple[Page, ...]:
        return tuple(Page(i, tuple(map(parse_slot, p))) for i, p in enumerate(self.raw[1:], 1))

    def to_raw(self) -> list:
        return deepcopy(self.raw)

    def walk(self):
        def visit(raw, path):
            node = parse_slot(raw)
            yield path, node
            if isinstance(node, Folder):
                for p, page in enumerate(raw["iconLists"]):
                    for s, child in enumerate(page):
                        yield from visit(child, (*path, p, s))

        for p, page in enumerate(self.raw):
            for s, raw in enumerate(page):
                yield from visit(raw, (p, s))

    def positions(self) -> dict[tuple, Slot]:
        return dict(self.walk())

    def apps(self) -> list[Icon]:
        return [node for _, node in self.walk() if isinstance(node, Icon)]


def validate_target(
    before: Layout,
    after: Layout,
    pins: tuple[str, ...] = (),
    *,
    restore: bool = False,
    folder_edits: tuple[dict, ...] = (),
) -> None:
    """Reject loss, payload edits, moved opaque nodes, dock changes and pin movement."""

    def inventory(layout):
        return Counter(
            (structural_fingerprint([[icon.raw]]) if restore else fingerprint([icon.raw]))
            for icon in layout.apps()
        )

    if inventory(before) != inventory(after):
        raise ValueError("Plan changes the app inventory or app payloads.")
    dock_equal = (
        structural_fingerprint([before.raw[0]]) == structural_fingerprint([after.raw[0]])
        if restore
        else before.raw[0] == after.raw[0]
    )
    if not dock_equal:
        raise ValueError("Plan changes the dock.")
    positions = after.positions()
    edits = {}
    destinations = set()
    original = before.positions()
    for edit in folder_edits:
        if not isinstance(edit, dict) or set(edit) != {"source", "target", "name"}:
            raise ValueError("Invalid explicit folder edit.")
        for key in ("source", "target"):
            path = edit[key]
            if (
                not isinstance(path, (list, tuple))
                or len(path) != 2
                or not all(type(index) is int and index >= 0 for index in path)
                or path[0] == 0
            ):
                raise ValueError("Folder edits need top-level Home Screen paths.")
        source, destination = tuple(edit["source"]), tuple(edit["target"])
        if (
            source in edits
            or destination in destinations
            or not isinstance(original.get(source), Folder)
            or not isinstance(edit["name"], str)
            or not 1 <= len(edit["name"]) <= 64
        ):
            raise ValueError("Conflicting or invalid explicit folder edit.")
        edits[source] = edit
        destinations.add(destination)
    for path, node in before.walk():
        if isinstance(node, Opaque) or (isinstance(node, Icon) and node.bundle_id in pins):
            other = positions.get(path)
            equal = (
                isinstance(other, Icon)
                and structural_fingerprint([[other.raw]]) == structural_fingerprint([[node.raw]])
                if restore and isinstance(node, Icon)
                else other == node
            )
            if not equal:
                raise ValueError("Plan moves a pinned app or an unknown node.")
        if isinstance(node, Folder) and not restore:
            edit = edits.get(path)
            other = positions.get(tuple(edit["target"]) if edit else path)
            if not isinstance(other, Folder):
                raise ValueError("Plan removes or moves an existing folder.")
            metadata = {k: v for k, v in node.raw.items() if k != "iconLists"}
            if edit:
                metadata["displayName"] = edit["name"]
            new_metadata = {k: v for k, v in other.raw.items() if k != "iconLists"}
            if metadata != new_metadata:
                raise ValueError("Plan changes existing folder metadata.")
    old_opaque = Counter(fingerprint([n.raw]) for _, n in before.walk() if isinstance(n, Opaque))
    new_opaque = Counter(fingerprint([n.raw]) for _, n in after.walk() if isinstance(n, Opaque))
    if old_opaque != new_opaque:
        raise ValueError("Plan changes unknown nodes.")
