from sborganize.model import Empty, Folder, Icon, Layout, Opaque
from sborganize.planner import Plan, loose_count
from sborganize.score import Score


def node_summary(node) -> dict:
    if isinstance(node, Icon):
        return {"kind": "app", "name": node.name, "bundle_id": node.bundle_id}
    if isinstance(node, Folder):
        return {
            "kind": "folder",
            "name": node.name,
            "pages": [[node_summary(n) for n in p] for p in node.pages],
        }
    return {"kind": "unknown" if isinstance(node, Opaque) else "empty"}


def layout_summary(layout: Layout) -> dict:
    return {
        "udid": layout.udid,
        "source": layout.source,
        "apps": len(layout.apps()),
        "dock": [node_summary(n) for n in layout.dock],
        "pages": [
            {"index": p.index, "slots": [node_summary(n) for n in p.slots]} for p in layout.pages
        ],
    }


def short_node(node) -> str:
    if isinstance(node, Icon):
        return node.name
    if isinstance(node, Folder):
        count = sum(isinstance(n, Icon) for p in node.pages for n in p)
        return f"{node.name} ({count} apps)"
    return "Unknown node (kept)"


def render_layout(layout: Layout) -> str:
    lines = [f"{len(layout.apps())} apps · {len(layout.pages)} pages", ""]
    dock = [short_node(n) for n in layout.dock if not isinstance(n, Empty)]
    lines.append("Dock    " + (" · ".join(dock) or "Empty"))
    for page in layout.pages:
        lines.append("")
        lines.append(f"Page {page.index}")
        nodes = [n for n in page.slots if not isinstance(n, Empty)]
        if not nodes:
            lines.append("  Empty")
        for node in nodes:
            lines.append(f"  {short_node(node)}")
            if isinstance(node, Folder):
                names = [short_node(n) for p in node.pages for n in p if not isinstance(n, Empty)]
                lines.append("    " + ", ".join(names))
    return "\n".join(lines)


def render_score(score: Score) -> str:
    value = (
        f"Grouping rate · {score.value}%" if score.scope == "grouping" else f"{score.value} / 100"
    )
    return value + "\n\n" + "\n".join(f"  {s}" for s in score.diagnoses)


def render_plan(plan: Plan, before: Score, after: Score, *, details=True, applying=False) -> str:
    if before.scope != after.scope:
        raise ValueError("Cannot compare scores with different scopes.")
    metric = (
        f"Grouping {before.value}% → {after.value}%"
        if before.scope == "grouping"
        else f"Score {before.value} → {after.value}"
    )
    lines = [
        f"Preview · {plan.provider}",
        f"{metric} · Pages {len(plan.before.pages)} → {len(plan.after.pages)}",
        f"Loose apps {loose_count(plan.before)} → {loose_count(plan.after)}",
    ]
    if before.scope == "grouping":
        lines.append("Grouping rate excludes page density and folder packing.")
    if plan.device_ready:
        lines.append(
            "USB-ready · loose positions after fixed anchors may compact; review all moves."
        )
    if plan.smart_info:
        info = plan.smart_info
        if info.get("available"):
            if info.get("reorganization"):
                lines.append(
                    f"Regroup · {len(info.get('accepted', []))} placements · "
                    "saved model advice + local rules; no new inference"
                )
            else:
                lines.append(
                    f"Smart · {info.get('provider')} · "
                    f"{len(info.get('accepted', []))} extra placements"
                )
            if info.get("generation_error"):
                lines.append(str(info["detail"]))
        else:
            lines.append(str(info.get("detail", "Model unavailable.")) + " Rules retained.")
    lines.append("")
    if not plan.changes:
        lines.append("No changes suggested.")
    for change in plan.changes:
        kind = change["kind"]
        if kind == "move":
            if details:
                lines.append(f"move     {change['name']}  →  {change['to']}")
        elif kind == "folder+":
            lines.append(f"folder+  {change['name']}  ·  {change['at']}")
        elif kind == "rename":
            lines.append(f"rename   {change['from']}  →  {change['name']}")
        elif kind == "folder-move":
            lines.append(f"folder   {change['name']}  ·  {change['from']} → {change['to']}")
        elif kind == "compact":
            lines.append(
                f"compact  {change['name']}  ·  "
                f"{change['pages_before']} → {change['pages_after']} inner pages"
            )
        elif kind == "page-":
            lines.append(f"page-    {change['page']}")
    if not details:
        lines.extend(compact_moves(plan))
    if before.value == after.value and plan.changes:
        message = (
            "Grouping rate unchanged after rounding; review the loose-app count."
            if before.scope == "grouping"
            else "Score unchanged; review the moves above."
        )
        lines.extend(["", message])
    if plan.unresolved:
        lines.extend(["", f"Kept for review · {len(plan.unresolved)}"])
        reasons = {
            "unknown_category": "category unknown",
            "ambiguous_folders": "multiple matching folders",
            "protected_folder": "folder contains a pin or unsupported node",
            "no_matching_folder": "no matching existing folder",
            "below_folder_threshold": "too few apps for a new folder",
            "missing_regional_folder": "regional folder missing; domain fallback blocked",
            "conflicting_regions": "same app appears in both regional groups",
        }
        for item in plan.unresolved:
            reason = reasons.get(item["reason"], item["reason"])
            if item.get("candidates"):
                reason += " · " + ", ".join(item["candidates"])
            lines.append(f"  {item['name']}  ·  {reason}")
    if plan.regional_review:
        lines.extend(["", f"Regional placement review · {len(plan.regional_review)}"])
        for item in plan.regional_review:
            fallback = (
                "a domain folder"
                if item.get("region") == "GLOBAL"
                else item.get("region", "regional folder")
            )
            target = ", ".join(item.get("candidates", [])) or fallback
            lines.append(
                f"  {item['name']}  ·  {item.get('from', 'existing folder')} → {target}"
                " · existing position kept"
            )
    footer = (
        "Dock, pins and unknown nodes protected. Writes require the safety checks below."
        if applying
        else "Dock, pins and unknown nodes kept. No phone writes."
    )
    lines.extend(["", footer])
    return "\n".join(lines)


def compact_moves(plan: Plan) -> list[str]:
    """Show every changed grouping, summarize within-group position shifts."""
    from collections import defaultdict

    old = defaultdict(list)
    new = defaultdict(list)
    for layout, target in ((plan.before, old), (plan.after, new)):
        for path, node in layout.walk():
            if isinstance(node, Icon):
                target[node.bundle_id].append((path, node.name))
    retained = {tuple(edit["source"]): tuple(edit["target"]) for edit in plan.folder_edits}
    destinations = plan.after.positions()
    grouped = defaultdict(list)
    shifts = 0
    for bundle, entries in old.items():
        for (source, name), (target, _) in zip(entries, new[bundle], strict=True):
            if source == target:
                continue
            same_group = (
                len(source) > 2
                and len(target) > 2
                and (retained.get(source[:2], source[:2]) == target[:2])
            )
            if same_group or (len(source) == len(target) == 2):
                shifts += 1
                continue
            parent = destinations.get(target[:2])
            group = parent.name if isinstance(parent, Folder) else "Home Screen"
            grouped[group].append(name)
    lines = []
    for group, names in grouped.items():
        lines.append(f"into     {group} · {len(names)} apps")
        lines.append("         " + ", ".join(names))
    if shifts:
        lines.append(f"\n{shifts} position changes within retained groups or loose slots.")
    if any(c["kind"] == "move" for c in plan.changes):
        lines.append("Add --details to see every position change.")
    return lines
