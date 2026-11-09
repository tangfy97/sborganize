"""Turn locally rechecked advice and explicit rules into a separate safe preview."""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace

from sborganize.model import (
    Folder,
    Icon,
    Layout,
    parse_slot,
    structural_fingerprint,
    validate_target,
)
from sborganize.planner import (
    BUNDLE_CATEGORIES,
    Plan,
    add_to_folder,
    describe_changes,
    editable_folder,
    folder_categories,
)
from sborganize.regions import app_region, folder_region
from sborganize.review import domain_matches, inventory, recheck_report


def refresh_reorganization(original, current, report, config):
    """Reuse reviewed advice only for additive top-level changes plus app bookkeeping."""
    if original.udid != current.udid or original.source != current.source:
        raise ValueError("Refreshed source must be the same device and source type.")
    if len(current.raw) < len(original.raw):
        raise ValueError("Current layout removed pages; generate a new review.")
    additions = []
    for p, page in enumerate(current.raw):
        old_page = original.raw[p] if p < len(original.raw) else []
        if len(page) < len(old_page) or structural_fingerprint([page[: len(old_page)]]) != (
            structural_fingerprint([old_page])
        ):
            raise ValueError("Existing layout structure changed; generate a new review.")
        for s in range(len(old_page), len(page)):
            node = parse_slot(page[s])
            if p == 0 or not isinstance(node, Icon):
                raise ValueError("Only newly appended Home Screen app icons can be refreshed.")
            additions.append(((p, s), node))
    identities = Counter(icon.bundle_id for icon in current.apps())
    if any(count != 1 for count in identities.values()):
        raise ValueError("Duplicate shortcuts need a new manual review before refreshing.")
    base = build_reorganization(original, report, config)
    payloads = {icon.bundle_id: icon.raw for icon in current.apps()}

    def update(node):
        parsed = parse_slot(node)
        if isinstance(parsed, Icon):
            return deepcopy(payloads[parsed.bundle_id])
        result = deepcopy(node)
        if isinstance(parsed, Folder):
            result["iconLists"] = [[update(child) for child in page] for page in node["iconLists"]]
        return result

    raw = [[update(node) for node in page] for page in base.after.raw]
    raw[0] = deepcopy(current.raw[0])
    accepted = list(base.smart_info["accepted"])
    pending = list(base.unresolved)
    for (p, s), icon in additions:
        region = app_region(icon, config, {})
        requested = (
            config.region_folders.get(region)
            if region in ("CN", "HK")
            else (config.folders.get(config.categories.get(icon.bundle_id)))
        )
        matches = [
            node
            for page in raw[1:]
            for node in page
            if isinstance(node, dict)
            and isinstance(parse_slot(node), Folder)
            and (requested or region in ("CN", "HK"))
            and (not requested or node["displayName"].casefold() == requested.casefold())
            and folder_region(node["displayName"], config)
            == (region if region in ("CN", "HK") else None)
            and editable_folder(parse_slot(node), config)
        ]
        if len(matches) == 1 and icon.bundle_id not in config.pins:
            add_to_folder(matches[0], [deepcopy(icon.raw)], replace(config, compact_folders=False))
            accepted.append(
                {
                    "name": icon.name,
                    "folder": matches[0]["displayName"],
                    "reason": "New app classified by an explicit local rule; no inference.",
                }
            )
        else:
            while len(raw) <= p:
                raw.append([])
            while len(raw[p]) <= s:
                raw[p].append(None)
            if raw[p][s] is not None:
                raise ValueError("Cannot preserve the position of a newly added app.")
            raw[p][s] = deepcopy(icon.raw)
            pending.append(
                {
                    "name": icon.name,
                    "bundle_id": icon.bundle_id,
                    "reason": "New app not in cloud review; original position retained.",
                }
            )
    target = Layout.from_raw(raw, current.udid, current.source)
    validate_target(current, target, config.pins)
    return replace(
        base,
        before=current,
        after=target,
        changes=describe_changes(current, target),
        unresolved=tuple(pending),
        smart_info={
            **base.smart_info,
            "accepted": accepted,
            "model_reviewed_apps": len(original.apps()),
            "locally_added_apps": len(additions),
        },
    )


def build_reorganization(layout, report, config):
    checked = recheck_report(layout, report, config)
    records, _, targets = inventory(layout, config)
    entries = sorted(
        [(path, node) for path, node in layout.walk() if isinstance(node, Icon)],
        key=lambda item: (item[1].bundle_id, item[1].name, item[0]),
    )
    paths = {record["app_id"]: entry for record, entry in zip(records, entries, strict=True)}
    decisions, new_groups, pending = {}, defaultdict(list), []
    for row in checked["apps"]:
        identifier = row["app_id"]
        if row["protected"]:
            continue
        region = row["region_hint"]
        explicit = config.categories.get(row["bundle_id"])
        known = explicit or BUNDLE_CATEGORIES.get(row["bundle_id"])
        requested = (
            config.region_folders.get(region)
            if region in ("CN", "HK")
            else (config.folders.get(explicit) if explicit else None)
        )
        matches = []
        if region in ("CN", "HK") or known:
            for fid, (_, _, folder) in targets.items():
                if not editable_folder(folder, config):
                    continue
                match = (
                    folder_region(folder.name, config) == region
                    if region in ("CN", "HK")
                    else (
                        not folder_region(folder.name, config)
                        and domain_matches(known, folder_categories(folder, config))
                    )
                )
                if match and (not requested or requested.casefold() == folder.name.casefold()):
                    matches.append(fid)
            if row["current_folder"] in matches:
                continue
            if len(matches) == 1:
                decisions[identifier] = matches[0]
                continue
            if explicit and requested and not matches and region not in ("CN", "HK"):
                if not any(
                    f.name.casefold() == requested.casefold() for _, _, f in targets.values()
                ):
                    new_groups[requested].append(identifier)
                    continue
            # Strong rules cannot silently fall back to a conflicting model destination.
            pending.append(
                {
                    "name": row["name"],
                    "bundle_id": row["bundle_id"],
                    "reason": "No unique destination for the known domain/region.",
                }
            )
        elif row["status"] == "move":
            destination = row["proposed_folder"]
            if editable_folder(targets[destination][2], config):
                decisions[identifier] = destination
            else:
                pending.append(
                    {
                        "name": row["name"],
                        "bundle_id": row["bundle_id"],
                        "reason": "Destination contains a pin or unsupported node.",
                    }
                )
        elif row["status"] == "review":
            pending.append(
                {
                    "name": row["name"],
                    "bundle_id": row["bundle_id"],
                    "reason": row.get("diagnostic") or row["reason"],
                }
            )

    for name, members in new_groups.items():
        if not config.create_folders or len(members) < config.new_folder_min_apps:
            raise ValueError("Explicit new folder needs creation enabled and enough apps: " + name)
        for identifier in members:
            decisions[identifier] = "new:" + name
    multiplicity = Counter(node.bundle_id for _, node in entries)
    if any(multiplicity[paths[identifier][1].bundle_id] != 1 for identifier in decisions):
        raise ValueError("Duplicate app shortcuts require manual review before regrouping.")

    raw = layout.to_raw()
    touched = set()
    for identifier in decisions:
        path, _ = paths[identifier]
        if len(path) == 2:
            raw[path[0]][path[1]] = None
        elif len(path) == 4:
            raw[path[0]][path[1]]["iconLists"][path[2]][path[3]] = None
            touched.add(path[:2])
        else:
            raise ValueError("Nested folder apps require manual review.")
    # Compact only edited source folders; pins/unknown children made these ineligible.
    for p, s in touched:
        raw[p][s]["iconLists"] = [
            [child for child in page if child is not None] for page in raw[p][s]["iconLists"]
        ]
    destinations = {fid: raw[p][s] for fid, (p, s, _) in targets.items()}
    for name, members in new_groups.items():
        node = {"listType": "folder", "displayName": name, "iconLists": [[]]}
        available = sorted(
            paths[identifier][0] for identifier in members if len(paths[identifier][0]) == 2
        )
        if available:
            p, s = available[0]
            raw[p][s] = node
        else:
            raw.append([node])
        destinations["new:" + name] = node
    accepted = []
    packing = replace(config, compact_folders=False)
    for identifier, destination in decisions.items():
        _, icon = paths[identifier]
        add_to_folder(destinations[destination], [icon.raw], packing)
        accepted.append(
            {
                "name": icon.name,
                "folder": destinations[destination]["displayName"],
                "reason": "Locally validated domain/region rule or model advice.",
            }
        )
    for p, s in touched:
        folder = raw[p][s]
        if not any(folder["iconLists"]):
            raise ValueError("Regrouping would empty an existing folder: " + folder["displayName"])
        # SpringBoard drops newly empty trailing folder pages on write.
        while len(folder["iconLists"]) > 1 and folder["iconLists"][-1] == []:
            folder["iconLists"].pop()
    after = Layout.from_raw(raw, layout.udid, layout.source)
    validate_target(layout, after, config.pins)
    return Plan(
        layout,
        after,
        describe_changes(layout, after),
        config.pins,
        provider="rules+openrouter",
        unresolved=tuple(pending),
        create_folders=bool(new_groups),
        compact_folders=False,
        smart_info={
            "reorganization": True,
            "provider": "openrouter",
            "available": True,
            "accepted": accepted,
            "detail": "Saved cloud advice rechecked locally; no new inference.",
            "review_source_fingerprint": checked["source_fingerprint"],
        },
    )
