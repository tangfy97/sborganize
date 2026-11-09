"""Deterministic planning with deliberately limited authority."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

from sborganize.config import Config
from sborganize.model import (
    Empty,
    Folder,
    Icon,
    Layout,
    decode_state,
    encode_state,
    fingerprint,
    parse_slot,
    validate_target,
)
from sborganize.regions import (
    REGION_LABELS,
    app_region,
    folder_region,
    placement_review,
    regional_references,
)
from sborganize.score import score_layout

BUNDLE_CATEGORIES = {
    "nl.cz.app": "Health",
    "com.go-jek.gopay": "Finance",
    "com.joybuy.jd": "Shopping",
    "com.apple.MobileSMS": "Social",
    "net.whatsapp.WhatsApp": "Social",
    "org.whispersystems.signal": "Social",
    "ph.telegra.Telegraph": "Social",
    "com.burbn.instagram": "Social",
    "com.toyopagroup.picaboo": "Social",
    "com.facebook.Facebook": "Social",
    "com.atebits.Tweetie2": "Social",
    "com.apple.mobilenotes": "Productivity",
    "com.apple.reminders": "Productivity",
    "com.apple.mobilecal": "Productivity",
    "notion.id": "Productivity",
    "com.tinyspeck.chatlyio": "Productivity",
    "com.todoist.ios": "Productivity",
    "com.microsoft.Office.Word": "Productivity",
    "com.microsoft.Office.Excel": "Productivity",
    "com.apple.Music": "Entertainment",
    "com.spotify.client": "Entertainment",
    "com.netflix.Netflix": "Entertainment",
    "com.google.ios.youtube": "Entertainment",
    "com.apple.podcasts": "Entertainment",
    "com.apple.tv": "Entertainment",
    "com.apple.Maps": "Travel",
    "com.google.Maps": "Travel",
    "com.ubercab.UberClient": "Travel",
    "com.airbnb.app": "Travel",
    "com.booking.BookingApp": "Travel",
    "com.revolut.revolut": "Finance",
    "com.monzo.monzo": "Finance",
    "com.paypal.ppclient": "Finance",
    "com.wise.Wise": "Finance",
    "com.apple.calculator": "Utilities",
    "com.apple.compass": "Utilities",
    "com.apple.VoiceMemos": "Utilities",
    "com.apple.measure": "Utilities",
    "com.apple.Preferences": "Utilities",
}
WORD_CATEGORIES = {
    "whatsapp": "Social",
    "signal": "Social",
    "telegram": "Social",
    "instagram": "Social",
    "slack": "Productivity",
    "notion": "Productivity",
    "todoist": "Productivity",
    "spotify": "Entertainment",
    "netflix": "Entertainment",
    "youtube": "Entertainment",
    "maps": "Travel",
    "uber": "Travel",
    "airbnb": "Travel",
    "booking": "Travel",
    "revolut": "Finance",
    "monzo": "Finance",
    "paypal": "Finance",
    "wise": "Finance",
    "calculator": "Utilities",
    "compass": "Utilities",
    "measure": "Utilities",
}
NAME_CATEGORIES = {
    **WORD_CATEGORIES,
    "mail": "Productivity",
    "gmail": "Productivity",
    "outlook": "Productivity",
    "google calendar": "Productivity",
    "virtual mail": "Productivity",
    "authenticator": "Security",
    "okta verify": "Security",
    "idme": "Security",
    "id.me": "Security",
    "digid": "Security",
    "bankid": "Security",
    "ibkr": "Finance",
    "interactive brokers": "Finance",
    "nordnet": "Finance",
    "imdb": "Entertainment",
    "didi": "Travel",
    "royal jordanian": "Travel",
    "fitness": "Health",
    "health": "Health",
    "watch": "Health",
    "njoy fitness app": "Health",
    "autosleep": "Health",
    "siri": "Utilities",
    "settings": "Utilities",
    "voice memos": "Utilities",
    "calendar": "Productivity",
    "notes": "Productivity",
    "reminders": "Productivity",
    "meta ai": "AI",
    "chatgpt": "AI",
    "claude": "AI",
    "gemini": "AI",
    "grok": "AI",
    "grok bot": "AI",
    "deepseek": "AI",
    "千问": "AI",
    "豆包": "AI",
}
FOLDER_ALIASES = {
    "social": "Social",
    "chat": "Social",
    "friends": "Social",
    "productivity": "Productivity",
    "work": "Productivity",
    "entertainment": "Entertainment",
    "media": "Entertainment",
    "travel": "Travel",
    "finance": "Finance",
    "money": "Finance",
    "utilities": "Utilities",
    "tools": "Utilities",
    "transport": "Transport",
    "flights": "Trips",
    "trips": "Trips",
}
TRAVEL_DOMAINS = {
    "maps": "Transport",
    "google maps": "Transport",
    "uber": "Transport",
    "bolt": "Transport",
    "ns": "Transport",
    "9292": "Transport",
    "trainline": "Transport",
    "db navigator": "Transport",
    "omio": "Transport",
    "airbnb": "Trips",
    "booking": "Trips",
    "booking.com": "Trips",
    "royal jordanian": "Trips",
    "klm": "Trips",
    "lufthansa": "Trips",
    "ryanair": "Trips",
    "sas": "Trips",
    "transavia": "Trips",
}


def travel_domain(icon: Icon, config: Config) -> str | None:
    if icon.bundle_id in config.categories:
        return None
    if icon.bundle_id == "com.didi.global.passenger":
        return "Transport"
    return TRAVEL_DOMAINS.get(icon.name.casefold().strip())


def category(icon: Icon, config: Config) -> str | None:
    if icon.bundle_id in config.categories:
        return config.categories[icon.bundle_id]
    if icon.bundle_id in BUNDLE_CATEGORIES:
        return BUNDLE_CATEGORIES[icon.bundle_id]
    name = icon.name.casefold().strip()
    if name in NAME_CATEGORIES:
        return NAME_CATEGORIES[name]
    if name in TRAVEL_DOMAINS:
        return "Travel"
    words = re.findall(r"[\w]+", icon.name.casefold())
    found = {WORD_CATEGORIES[w] for w in words if w in WORD_CATEGORIES}
    return next(iter(found)) if len(found) == 1 else None


def folder_categories(node: Folder, config: Config) -> set[str]:
    """Learn a mixed/emoji folder's roles from multiple known peer apps."""
    region = folder_region(node.name, config)
    if region:
        return {f"region:{region}"}
    explicit = {
        key for key, name in config.folders.items() if name.casefold() == node.name.casefold()
    }
    named = FOLDER_ALIASES.get(node.name.casefold())
    if named:
        return explicit | {named}
    # Repeated copies of one app must not manufacture evidence.
    known = {}
    for page in node.pages:
        for child in page:
            if isinstance(child, Icon):
                key = category(child, config)
                if key:
                    known[child.bundle_id] = {key}
                    detail = travel_domain(child, config)
                    if detail:
                        known[child.bundle_id].add(detail)
    votes = Counter(key for roles in known.values() for key in roles)
    return explicit | {
        key for key, count in votes.items() if count >= 2 and count / len(known) >= 0.25
    }


def loose_count(layout: Layout) -> int:
    return sum(isinstance(node, Icon) for page in layout.pages for node in page.slots)


def editable_folder(node: Folder, config: Config) -> bool:
    return all(
        isinstance(child, Empty) or (isinstance(child, Icon) and child.bundle_id not in config.pins)
        for page in node.pages
        for child in page
    )


def packed(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def add_to_folder(folder: dict, additions: list, config: Config) -> None:
    pages = folder["iconLists"]
    if config.compact_folders:
        items = [item for page in pages for item in page] + additions
        folder["iconLists"] = packed(items, config.folder_page_size)
        return
    # Preserve every existing app's path. Fill holes or append at the observed capacity.
    capacity = max([config.folder_page_size, *(len(page) for page in pages)])
    for item in additions:
        empty = next(
            (
                (p, s)
                for p, page in enumerate(pages)
                for s, raw in enumerate(page)
                if isinstance(parse_slot(raw), Empty)
            ),
            None,
        )
        if empty is not None:
            pages[empty[0]][empty[1]] = item
            continue
        available = next((page for page in pages if len(page) < capacity), None)
        if available is not None:
            available.append(item)
        else:
            pages.append([item])


@dataclass(frozen=True)
class Plan:
    before: Layout
    after: Layout
    changes: list[dict]
    pins: tuple[str, ...]
    provider: str = "rules"
    unresolved: tuple[dict, ...] = ()
    create_folders: bool = True
    compact_folders: bool = True
    regional_review: tuple[dict, ...] = ()
    smart_info: dict = field(default_factory=dict)
    device_ready: bool = False
    folder_edits: tuple[dict, ...] = ()

    def score_config(self, config: Config) -> Config:
        return replace(
            config, create_folders=self.create_folders, compact_folders=self.compact_folders
        )

    def to_dict(self, config: Config) -> dict:
        config = self.score_config(config)
        return {
            "schema_version": 1,
            "udid": self.before.udid,
            "source": self.before.source,
            "source_fingerprint": fingerprint(self.before.raw),
            "target_fingerprint": fingerprint(self.after.raw),
            "source_state_plist": encode_state(self.before.raw),
            "target_state_plist": encode_state(self.after.raw),
            "pins": list(self.pins),
            "provider": self.provider,
            "changes": self.changes,
            "score_before": score_layout(self.before, config).to_dict(),
            "score_after": score_layout(self.after, config).to_dict(),
            "pages_before": len(self.before.pages),
            "pages_after": len(self.after.pages),
            "loose_before": loose_count(self.before),
            "loose_after": loose_count(self.after),
            "unresolved": list(self.unresolved),
            "regional_review": list(self.regional_review),
            "smart": self.smart_info,
            "device_ready": self.device_ready,
            "folder_edits": list(self.folder_edits),
            "policy": {
                "create_folders": config.create_folders,
                "compact_folders": config.compact_folders,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        if isinstance(data, dict) and data.get("kind") == "organization_review":
            raise ValueError("An organization review is advisory, not an apply plan.")
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported plan format.")
        before = Layout.from_raw(
            decode_state(data["source_state_plist"]), data["udid"], data["source"]
        )
        after = Layout.from_raw(
            decode_state(data["target_state_plist"]), data["udid"], data["source"]
        )
        if (
            fingerprint(before.raw) != data["source_fingerprint"]
            or fingerprint(after.raw) != data["target_fingerprint"]
        ):
            raise ValueError("Plan fingerprint mismatch. Generate a new plan.")
        pins = data.get("pins", [])
        if not isinstance(pins, list) or not all(isinstance(pin, str) for pin in pins):
            raise ValueError("Invalid pins in plan.")
        folder_edits = data.get("folder_edits", [])
        if not isinstance(folder_edits, list):
            raise ValueError("Invalid explicit folder edits.")
        validate_target(before, after, tuple(pins), folder_edits=tuple(folder_edits))
        policy = data.get("policy", {})
        provider = data.get("provider", "rules")
        info = data.get("smart", {})
        if type(data.get("device_ready", False)) is not bool:
            raise ValueError("Invalid device-ready marker.")
        if provider not in ("rules", "rules+apple-on-device", "rules+openrouter") or not isinstance(
            info, dict
        ):
            raise ValueError("Invalid model metadata in plan.")
        if not isinstance(policy, dict) or any(
            type(policy.get(key, True)) is not bool for key in ("create_folders", "compact_folders")
        ):
            raise ValueError("Invalid planning policy.")
        unresolved = data.get("unresolved", [])
        regional_review = data.get("regional_review", [])
        for review in (unresolved, regional_review):
            if not isinstance(review, list) or not all(
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("reason"), str)
                and isinstance(item.get("bundle_id"), str)
                and isinstance(item.get("candidates", []), list)
                and all(isinstance(name, str) for name in item.get("candidates", []))
                for item in review
            ):
                raise ValueError("Invalid review items in plan.")
        return cls(
            before,
            after,
            describe_changes(before, after, folder_edits=tuple(folder_edits)),
            tuple(pins),
            unresolved=tuple(unresolved),
            create_folders=policy.get("create_folders", True),
            compact_folders=policy.get("compact_folders", True),
            regional_review=tuple(regional_review),
            provider=provider,
            smart_info=info,
            device_ready=data.get("device_ready", False),
            folder_edits=tuple(folder_edits),
        )


def location(path: tuple, layout: Layout) -> str:
    if path[0] == 0:
        return "dock"
    if len(path) == 2:
        return f"page {path[0]}, slot {path[1] + 1}"
    parent = layout.positions().get(path[:2])
    name = parent.name if isinstance(parent, Folder) else "folder"
    return f"{name}, page {path[2] + 1}, slot {path[3] + 1}"


def describe_changes(before: Layout, after: Layout, *, folder_edits=()) -> list[dict]:
    changes = []
    old_folders = {p: n for p, n in before.walk() if isinstance(n, Folder)}
    sources = {tuple(edit["target"]): tuple(edit["source"]) for edit in folder_edits}
    for path, node in after.walk():
        source = sources.get(path, path)
        previous = old_folders.get(source)
        if isinstance(node, Folder) and previous is None:
            changes.append({"kind": "folder+", "name": node.name, "at": location(path, after)})
        elif isinstance(node, Folder):
            if node.name != previous.name:
                changes.append({"kind": "rename", "from": previous.name, "name": node.name})
            if source != path:
                changes.append(
                    {
                        "kind": "folder-move",
                        "name": node.name,
                        "from": location(source, before),
                        "to": location(path, after),
                    }
                )
            if len(node.pages) >= len(previous.pages):
                continue
            changes.append(
                {
                    "kind": "compact",
                    "name": node.name,
                    "pages_before": len(previous.pages),
                    "pages_after": len(node.pages),
                }
            )
    old = defaultdict(list)
    new = defaultdict(list)
    icons = {}
    for layout, positions in ((before, old), (after, new)):
        for path, node in layout.walk():
            if isinstance(node, Icon):
                key = fingerprint([node.raw])
                positions[key].append(path)
                icons[key] = node
    for key, paths in old.items():
        removed = [p for p in paths if p not in new[key]]
        added = [p for p in new[key] if p not in paths]
        for source, target in zip(removed, added, strict=True):
            changes.append(
                {
                    "kind": "move",
                    "name": icons[key].name,
                    "bundle_id": icons[key].bundle_id,
                    "from": location(source, before),
                    "to": location(target, after),
                }
            )
    for index in range(len(after.pages) + 1, len(before.pages) + 1):
        changes.append({"kind": "page-", "page": index})
    return changes


def build_plan(layout: Layout, config: Config) -> Plan:
    raw = layout.to_raw()
    destinations = defaultdict(list)
    folders = {}
    all_folder_names = set()
    unresolved = []
    references = regional_references(layout, config)

    def keep(candidates, reason, key=None, matches=()):
        for _, _, payload in candidates:
            icon = parse_slot(payload)
            unresolved.append(
                {
                    "name": icon.name,
                    "bundle_id": icon.bundle_id,
                    "category": key,
                    "domain": category(icon, config),
                    "region": app_region(icon, config, references),
                    "reason": reason,
                    "candidates": [folders[path].name for path in matches],
                }
            )

    for p, page in enumerate(raw[1:], 1):
        for s, payload in enumerate(page):
            node = parse_slot(payload)
            if isinstance(node, Folder):
                all_folder_names.add(node.name.casefold())
                folders[p, s] = node
                for key in sorted(folder_categories(node, config)):
                    destinations[key].append((p, s))
                if config.compact_folders and editable_folder(node, config):
                    items = [n.raw for fp in node.pages for n in fp if not isinstance(n, Empty)]
                    payload["iconLists"] = packed(items, config.folder_page_size)
    groups = defaultdict(list)
    for p, page in enumerate(raw[1:], 1):
        for s, payload in enumerate(page):
            node = parse_slot(payload)
            if isinstance(node, Icon) and node.bundle_id not in config.pins:
                region = app_region(node, config, references)
                if region == "CONFLICT":
                    keep([(p, s, payload)], "conflicting_regions")
                    continue
                key = f"region:{region}" if region in REGION_LABELS else category(node, config)
                detail = travel_domain(node, config)
                if region not in REGION_LABELS and detail and destinations[detail]:
                    key = detail
                if key:
                    groups[key].append((p, s, payload))
                else:
                    keep([(p, s, payload)], "unknown_category")
    for key, candidates in groups.items():
        matches = destinations[key]
        regional_key = key.removeprefix("region:") if key.startswith("region:") else None
        requested = (
            config.region_folders.get(regional_key) if regional_key else config.folders.get(key)
        )
        if requested:
            matches = [
                path for path in matches if folders[path].name.casefold() == requested.casefold()
            ]
        if len(matches) > 1:
            keep(candidates, "ambiguous_folders", key, matches)
            continue
        if matches:
            p, s = matches[0]
            if not editable_folder(folders[p, s], config):
                keep(candidates, "protected_folder", key, matches)
                continue
            folder = raw[p][s]
        else:
            name = requested or (REGION_LABELS[regional_key] if regional_key else key)
            if not config.create_folders:
                keep(
                    candidates,
                    "missing_regional_folder" if regional_key else "no_matching_folder",
                    key,
                )
                continue
            if len(candidates) < config.new_folder_min_apps or name.casefold() in all_folder_names:
                keep(
                    candidates,
                    "below_folder_threshold"
                    if len(candidates) < config.new_folder_min_apps
                    else "no_matching_folder",
                    key,
                )
                continue
            p, s, _ = candidates[0]
            folder = {"listType": "folder", "displayName": name, "iconLists": []}
            all_folder_names.add(name.casefold())
        additions = []
        for source_p, source_s, payload in candidates:
            raw[source_p][source_s] = None
            additions.append(payload)
        add_to_folder(folder, additions, config)
        raw[p][s] = folder
    # Only trailing empty pages can disappear; other positions are anchors.
    while len(raw) > 1 and all(isinstance(parse_slot(n), Empty) for n in raw[-1]):
        raw.pop()
    target = Layout.from_raw(raw, layout.udid, layout.source)
    validate_target(layout, target, config.pins)
    return Plan(
        layout,
        target,
        describe_changes(layout, target),
        config.pins,
        unresolved=tuple(unresolved),
        create_folders=config.create_folders,
        compact_folders=config.compact_folders,
        regional_review=placement_review(layout, config, references),
    )
