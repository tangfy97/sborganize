"""Mandatory, testable backup / confirmation / round-trip protocol."""

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sborganize.model import Layout, fingerprint, structural_fingerprint, validate_target
from sborganize.storage import layout_document, layout_from_document, read_json, write_json


class SafetyError(RuntimeError):
    pass


class Device(Protocol):
    udid: str
    source: str

    async def read(self) -> Layout: ...
    async def write(self, raw: list) -> None: ...


def backup_layout(layout: Layout, root: Path) -> Path:
    # Device identifiers never become unchecked path components.
    device_key = hashlib.sha256(f"{layout.source}:{layout.udid}".encode()).hexdigest()[:16]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = root / "backups" / f"{timestamp}-{device_key}-{uuid4().hex[:8]}.json"
    data = layout_document(layout)
    data.update(
        {
            "kind": "backup",
            "captured_at": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint(layout.raw),
        }
    )
    write_json(path, data)
    return path


def load_backup(path: Path) -> Layout:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("kind") != "backup":
        raise ValueError("Not an sborganize backup.")
    layout = layout_from_document(data, fixture=False)
    if fingerprint(layout.raw) != data.get("fingerprint"):
        raise SafetyError("Backup fingerprint mismatch.")
    return layout


def latest_backup(root: Path, udid: str, source: str) -> Path:
    for path in sorted((root / "backups").glob("*.json"), reverse=True):
        data = read_json(path)
        if data.get("udid") == udid and data.get("source") == source:
            return path
    raise SafetyError("No backup for this device. Supply --backup PATH.")


async def apply_target(
    device: Device,
    expected: Layout,
    target: Layout,
    root: Path,
    confirm: Callable[[Path], bool],
    pins: tuple[str, ...] = (),
    *,
    restore: bool = False,
    folder_edits: tuple[dict, ...] = (),
    progress: Callable[[str], None] | None = None,
) -> Path:
    if expected.udid != device.udid or expected.source != device.source:
        raise SafetyError("Plan belongs to a different device or fixture. Generate a new plan.")
    if target.udid != expected.udid or target.source != expected.source:
        raise SafetyError("Target belongs to a different device or fixture.")
    validate_target(expected, target, pins, restore=restore, folder_edits=folder_edits)
    current = await device.read()
    if fingerprint(current.raw) != fingerprint(expected.raw):
        raise SafetyError("Layout changed since this plan. Generate a new plan before applying.")
    backup = backup_layout(current, root)
    if fingerprint(load_backup(backup).raw) != fingerprint(current.raw):
        raise SafetyError("Backup verification failed. No writes made.")
    # Confirm before the unchanged write too; declining must perform zero writes.
    if not confirm(backup):
        raise SafetyError(f"Cancelled. No writes made. Backup: {backup}")
    try:
        fresh = await device.read()
        if fingerprint(fresh.raw) != fingerprint(current.raw):
            raise SafetyError("Layout changed during confirmation. Generate a new plan.")
        if progress:
            progress("1/3  Checking unchanged round-trip")
        await device.write(current.to_raw())
        if not await verify_readback(device, current):
            raise SafetyError("Unchanged round-trip mismatch. Target was not written.")
        if progress:
            progress("2/3  Writing the approved layout")
        await device.write(target.to_raw())
        if progress:
            progress("3/3  Verifying device read-back")
        if not await verify_readback(device, target):
            raise SafetyError("Read-back mismatch. Layout may have reflowed; restore the backup.")
    except Exception as exc:
        # Preserve the backup location for *any* transport/write failure.
        raise SafetyError(f"{exc} Backup kept: {backup}") from exc
    return backup


async def verify_readback(device: Device, expected: Layout) -> bool:
    deadline = asyncio.get_running_loop().time() + getattr(device, "settle_timeout", 0)
    signature = structural_fingerprint(expected.raw)
    while True:
        if structural_fingerprint((await device.read()).raw) == signature:
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.25)
