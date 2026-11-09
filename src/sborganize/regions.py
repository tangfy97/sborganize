"""Offline service-region rules, independent of language or publisher origin."""

from collections import defaultdict

from sborganize.config import Config
from sborganize.model import Folder, Icon, Layout

REGION_LABELS = {"CN": "🇨🇳", "HK": "HK"}
REGION_ALIASES = {
    "🇨🇳": "CN",
    "china": "CN",
    "mainland china": "CN",
    "中国": "CN",
    "中国大陆": "CN",
    "🇭🇰": "HK",
    "hk": "HK",
    "hong kong": "HK",
    "香港": "HK",
}
# Public App Store IDs 554499054 / 1362398401; see docs/research/classification.md.
BUNDLE_REGIONS = {
    "com.xiaojukeji.didi": "CN",
    "com.didi.global.passenger": "GLOBAL",
    "com.go-jek.gopay": "GLOBAL",
    "com.octopuscards.tourist": "HK",
    "com.joybuy.jd": "GLOBAL",
}
# Narrow local-service cues. Never classify from script, locale or bundle-ID suffix.
SERVICE_NAMES = {
    "美团外卖": "CN",
    "meituan": "CN",
    "淘宝闪购": "CN",
    "dianping": "CN",
    "amap": "CN",
    "railway12306": "CN",
    "拼多多": "CN",
    "上海交通卡": "CN",
    "国家政务服务平台": "CN",
    "皖事通": "CN",
    "jd": "CN",
    "盒马": "CN",
    "国家网络身份认证": "CN",
    "za bank": "HK",
    "octopus": "HK",
    "iam smart": "HK",
    "club sim": "HK",
    "hk e-channel": "HK",
    "八達通": "HK",
    "智方便": "HK",
}


def folder_region(name: str, config: Config) -> str | None:
    for region, target in config.region_folders.items():
        if name.casefold() == target.casefold():
            return region
    return REGION_ALIASES.get(name.casefold().strip())


def regional_references(layout: Layout, config: Config) -> dict[str, set[str]]:
    references = defaultdict(set)
    for page in layout.pages:
        for node in page.slots:
            if isinstance(node, Folder):
                region = folder_region(node.name, config)
                if region:
                    for inner_page in node.pages:
                        for child in inner_page:
                            if isinstance(child, Icon):
                                references[child.bundle_id].add(region)
    return dict(references)


def app_region(icon: Icon, config: Config, references: dict[str, set[str]]) -> str | None:
    if icon.bundle_id in config.regions:
        return config.regions[icon.bundle_id]
    if icon.bundle_id in BUNDLE_REGIONS:
        return BUNDLE_REGIONS[icon.bundle_id]
    service = SERVICE_NAMES.get(icon.name.casefold().strip())
    if service:
        return service
    learned = references.get(icon.bundle_id, set())
    if len(learned) > 1:
        return "CONFLICT"
    if learned:
        return next(iter(learned))
    return None


def placement_review(layout: Layout, config: Config, references) -> tuple[dict, ...]:
    """Report regional exceptions without moving already-grouped apps."""
    positions = layout.positions()
    targets = defaultdict(list)
    for page in layout.pages:
        for node in page.slots:
            if isinstance(node, Folder):
                region = folder_region(node.name, config)
                if region and (
                    region not in config.region_folders
                    or node.name.casefold() == config.region_folders[region].casefold()
                ):
                    targets[region].append(node.name)
    review = []
    for path, node in layout.walk():
        if path[0] == 0 or len(path) == 2 or not isinstance(node, Icon):
            continue
        region = app_region(node, config, references)
        current = positions[path[:2]]
        current_region = folder_region(current.name, config)
        if (region in REGION_LABELS and current_region != region) or (
            region == "GLOBAL" and current_region
        ):
            review.append(
                {
                    "name": node.name,
                    "bundle_id": node.bundle_id,
                    "region": region,
                    "from": current.name,
                    "reason": "pinned"
                    if node.bundle_id in config.pins
                    else "kept_existing_position",
                    "candidates": targets[region],
                }
            )
    return tuple(review)
