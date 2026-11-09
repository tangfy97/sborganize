"""Prepare a reviewable XML-plist target without inventing unsupported empty-slot markers."""

import plistlib
from dataclasses import replace

from sborganize.model import Folder, Icon, Layout, Opaque, validate_target
from sborganize.planner import Plan, describe_changes


def validate_wire_state(raw: list) -> None:
    try:
        plistlib.dumps({"command": "setIconState", "iconState": raw}, fmt=plistlib.FMT_XML)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "Layout cannot be encoded for USB. Anchored gaps or unsupported plist values "
            "remain; no writes were made."
        ) from exc


def prepare_device_plan(plan: Plan) -> Plan:
    raw = plan.after.to_raw()
    anchors = {}
    for path, node in plan.before.walk():
        if (
            len(path) == 2
            and path[0] > 0
            and (
                isinstance(node, (Folder, Opaque))
                or isinstance(node, Icon)
                and node.bundle_id in plan.pins
            )
        ):
            anchors[path[0]] = max(anchors.get(path[0], -1), path[1])
    for p in range(1, len(raw)):
        boundary = anchors.get(p, -1) + 1
        raw[p] = raw[p][:boundary] + [item for item in raw[p][boundary:] if item is not None]
    while len(raw) > 1 and not raw[-1]:
        raw.pop()
    target = Layout.from_raw(raw, plan.before.udid, plan.before.source)
    validate_target(plan.before, target, plan.pins, folder_edits=plan.folder_edits)
    validate_wire_state(plan.before.raw)
    validate_wire_state(target.raw)
    return replace(
        plan,
        after=target,
        changes=describe_changes(plan.before, target, folder_edits=plan.folder_edits),
        device_ready=True,
    )
