"""Explicit, exhaustive per-app domain policies. No model or network calls."""

from collections import Counter
from copy import deepcopy

from sborganize.config import Config
from sborganize.model import Folder, Icon, Layout, fingerprint, validate_target
from sborganize.planner import Plan, describe_changes, editable_folder, packed


def emoji_label(label):
    def emoji(char):
        value = ord(char)
        return 0x1F000 <= value <= 0x1FAFF or 0x2600 <= value <= 0x27BF

    return (
        isinstance(label, str)
        and 1 <= len(label) <= 64
        and any(map(emoji, label))
        and all(emoji(char) or char in ("\ufe0f", "\u200d", "\u20e3") for char in label)
    )


def export_policy(layout: Layout, config: Config) -> dict:
    """Capture current membership as a draft; loose apps stay explicitly unresolved."""
    positions = layout.positions()
    folders = []
    identifiers = {}
    for path, node in layout.walk():
        if not isinstance(node, Folder):
            continue
        if len(path) != 2 or path[0] == 0 or not editable_folder(node, config):
            raise ValueError("Policy export requires editable top-level folders without pins.")
        identifier = f"group_{len(folders) + 1}"
        identifiers[path] = identifier
        folders.append(
            {"id": identifier, "name": node.name, "source": list(path), "target": list(path)}
        )
    if not folders:
        raise ValueError("No existing folders. Start with sborganize plan, not policy export.")
    apps = {}
    for path, node in layout.walk():
        if not isinstance(node, Icon):
            continue
        if node.bundle_id in apps:
            raise ValueError("Duplicate app shortcuts require manual review before policy export.")
        target = "dock" if path[0] == 0 else identifiers.get(path[:2], "REVIEW")
        current = positions.get(path[:2])
        reason = (
            "Keep the existing Dock entry."
            if target == "dock"
            else (
                "Review current placement in " + current.name
                if isinstance(current, Folder)
                else "Choose a destination after identifying this app."
            )
        )
        apps[node.bundle_id] = {"name": node.name, "folder": target, "reason": reason}
    return {
        "schema_version": 1,
        "kind": "organization_policy",
        "source_fingerprint": fingerprint(layout.raw),
        "folder_page_size": 9,
        "folders": folders,
        "apps": apps,
        "notes": "DRAFT: review every app and reason; use unique emoji folder names; "
        "replace REVIEW with a folder ID before planning.",
    }


def build_policy_plan(layout: Layout, policy: dict, config: Config) -> tuple[Plan, dict]:
    if (
        not isinstance(policy, dict)
        or policy.get("schema_version") != 1
        or (policy.get("kind") != "organization_policy")
    ):
        raise ValueError("Expected a schema_version=1 organization policy.")
    if policy.get("source_fingerprint") != fingerprint(layout.raw):
        raise ValueError("Policy belongs to a different snapshot. Review the current inventory.")
    size = policy.get("folder_page_size", 9)
    if type(size) is not int or not 1 <= size <= 100:
        raise ValueError("Invalid policy folder page size.")
    folders = policy.get("folders")
    assignments = policy.get("apps")
    if not isinstance(folders, list) or not isinstance(assignments, dict):
        raise ValueError("Policy needs folders and an exhaustive app map.")
    positions = layout.positions()
    original_folders = {path: node for path, node in layout.walk() if isinstance(node, Folder)}
    if any(len(path) != 2 or path[0] == 0 for path in original_folders):
        raise ValueError("Nested or dock folders need a manual policy review.")
    sources, targets, ids, names, edits = set(), set(), set(), set(), []
    catalog = {}
    for folder in folders:
        if not isinstance(folder, dict):
            raise ValueError("Invalid policy folder.")
        identifier, name = folder.get("id"), folder.get("name")
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier in ids
            or (identifier == "dock" or not emoji_label(name) or name in names)
        ):
            raise ValueError("Folder IDs/names must be unique and names must contain only emoji.")
        for key in ("source", "target"):
            path = folder.get(key)
            if (
                not isinstance(path, list)
                or len(path) != 2
                or not all(type(i) is int and i >= 0 for i in path)
                or path[0] == 0
            ):
                raise ValueError("Policy folders need top-level Home Screen source/target paths.")
        source, target = tuple(folder["source"]), tuple(folder["target"])
        if source in sources or target in targets or source not in original_folders:
            raise ValueError("Folder source/target paths must be unique existing folder slots.")
        if not editable_folder(original_folders[source], config):
            raise ValueError("Cannot repack a folder containing pins or unsupported nodes.")
        sources.add(source)
        targets.add(target)
        ids.add(identifier)
        names.add(name)
        catalog[identifier] = folder
        edits.append({"source": list(source), "target": list(target), "name": name})
    if sources != set(original_folders) or targets != sources:
        raise ValueError("Explicit redesign must reuse every existing folder and folder slot once.")
    adjacent = policy.get("adjacent_groups", [])
    if not isinstance(adjacent, list):
        raise ValueError("adjacent_groups must be a list of pairs.")
    for pair in adjacent:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(identifier, str) and identifier in catalog for identifier in pair)
        ):
            raise ValueError("Adjacent group IDs must identify two policy folders.")
        left, right = (catalog[identifier]["target"] for identifier in pair)
        if left[0] != right[0] or right[1] != left[1] + 1:
            raise ValueError("Requested adjacent groups are not next to each other.")
    apps = [(path, node) for path, node in layout.walk() if isinstance(node, Icon)]
    counts = Counter(node.bundle_id for _, node in apps)
    if any(count != 1 for count in counts.values()) or set(assignments) != set(counts):
        raise ValueError("Policy must cover every unique app exactly once, including dock apps.")
    groups = {identifier: [] for identifier in ids}
    audit = []
    for path, icon in apps:
        assignment = assignments[icon.bundle_id]
        if (
            not isinstance(assignment, dict)
            or assignment.get("name") != icon.name
            or not isinstance(assignment.get("reason"), str)
            or not assignment["reason"].strip()
        ):
            raise ValueError("Every policy app needs its exact current name and a nonempty reason.")
        target = assignment.get("folder")
        if not isinstance(target, str):
            raise ValueError("App destination must be a folder ID string.")
        rank = assignment.get("rank", 1000)
        if type(rank) is not int or not 0 <= rank <= 10000:
            raise ValueError("App rank must be an integer from 0 to 10000.")
        protected = path[0] == 0 or icon.bundle_id in config.pins
        if protected and target != "dock":
            raise ValueError("A policy cannot move dock or pinned apps.")
        if not protected and target not in ids:
            raise ValueError("Policy app has an unknown folder ID.")
        if target == "dock" and path[0] != 0:
            raise ValueError("A pinned Home Screen app needs a policy retaining its exact path.")
        if not protected:
            groups[target].append((icon.bundle_id, deepcopy(icon.raw)))
        current = positions.get(path[:2])
        audit.append(
            {
                "name": icon.name,
                "bundle_id": icon.bundle_id,
                "current": "Dock"
                if path[0] == 0
                else (current.name if isinstance(current, Folder) else "Loose"),
                "target": "Dock" if target == "dock" else catalog[target]["name"],
                "reason": assignment["reason"],
                "rank": rank,
            }
        )
    raw = layout.to_raw()
    for path, _icon in apps:
        if len(path) == 2 and path[0] > 0:
            raw[path[0]][path[1]] = None
    for identifier, folder in catalog.items():
        members = groups[identifier]
        if not members:
            raise ValueError("Explicit redesign would leave an empty folder: " + folder["name"])
        # Optional explicit rank, then current inventory order; no network-derived sorting.
        members.sort(key=lambda item: assignments[item[0]].get("rank", 1000))
        node = deepcopy(original_folders[tuple(folder["source"])].raw)
        node["displayName"] = folder["name"]
        node["iconLists"] = packed([raw_icon for _, raw_icon in members], size)
        p, s = folder["target"]
        raw[p][s] = node
    after = Layout.from_raw(raw, layout.udid, layout.source)
    validate_target(layout, after, config.pins, folder_edits=tuple(edits))
    plan = Plan(
        layout,
        after,
        describe_changes(layout, after, folder_edits=edits),
        config.pins,
        create_folders=False,
        compact_folders=True,
        folder_edits=tuple(edits),
    )
    summaries = [
        {
            "id": folder["id"],
            "name": folder["name"],
            "count": len(groups[folder["id"]]),
            "pages": list(map(len, raw[folder["target"][0]][folder["target"][1]]["iconLists"])),
            "home_page": folder["target"][0],
            "home_slot": folder["target"][1] + 1,
        }
        for folder in folders
    ]
    return plan, {
        "schema_version": 1,
        "kind": "organization_policy_audit",
        "source_fingerprint": fingerprint(layout.raw),
        "apps": audit,
        "folders": summaries,
        "app_count": len(audit),
        "complete": True,
        "model_requests": 0,
    }
