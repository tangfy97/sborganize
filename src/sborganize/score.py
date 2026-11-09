from dataclasses import asdict, dataclass, field

from sborganize.config import Config
from sborganize.model import Empty, Folder, Icon, Layout


@dataclass(frozen=True)
class Score:
    value: int
    penalties: dict[str, int]
    diagnoses: list[str]
    scope: str = "layout"
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def score_layout(layout: Layout, config: Config) -> Score:
    pages = layout.pages
    loose = sum(isinstance(n, Icon) for page in pages for n in page.slots)
    apps = sum(isinstance(node, Icon) for path, node in layout.walk() if path[0] != 0)
    counts = {"home_screen_apps": apps, "loose_apps": loose, "grouped_apps": apps - loose}
    if not config.create_folders and not config.compact_folders:
        percentage = round(100 * (apps - loose) / apps) if apps else 100
        diagnoses = [
            f"{apps - loose} of {apps} recognized Home Screen apps are in folders.",
            f"{loose} loose {'app' if loose == 1 else 'apps'} outside folders.",
            "Page density and folder packing are not scored in existing-only mode.",
        ]
        return Score(
            percentage,
            {"loose_ratio": 100 - percentage},
            diagnoses,
            scope="grouping",
            counts=counts,
        )
    # 24 is an explainable scoring heuristic, never a placement capacity.
    capacity = sum(max(24, len(page.slots)) for page in pages)
    occupied = sum(not isinstance(n, Empty) for page in pages for n in page.slots)
    sparsity = (capacity - occupied) / capacity if capacity else 0
    folders = [node for _, node in layout.walk() if isinstance(node, Folder)]
    bloat = sum(
        max(
            0,
            len(f.pages)
            - max(
                1,
                (
                    sum(not isinstance(n, Empty) for p in f.pages for n in p)
                    + config.folder_page_size
                    - 1
                )
                // config.folder_page_size,
            ),
        )
        for f in folders
    )
    accessible = {
        node.bundle_id
        for path, node in layout.walk()
        if isinstance(node, Icon) and len(path) == 2 and path[0] in (0, 1)
    }
    missing_pins = len(set(config.pins) - accessible)
    penalties = {
        "page_tax": min(20, max(0, len(pages) - config.target_pages) * 7),
        "loose_ratio": round(35 * loose / apps) if apps else 0,
        "sparsity": round(20 * sparsity),
        "folder_bloat": min(15, bloat * 5),
        "pin_health": min(10, missing_pins * 5),
    }
    diagnoses = []
    if loose:
        diagnoses.append(f"{loose} loose {'app' if loose == 1 else 'apps'} outside folders.")
    if sparsity > 0.5 and pages:
        diagnoses.append("Home Screen pages are sparse.")
    if bloat:
        diagnoses.append(f"{bloat} excess folder pages can be packed.")
    if penalties["page_tax"]:
        diagnoses.append(f"{len(pages)} pages; soft target is {config.target_pages}.")
    if missing_pins:
        diagnoses.append(f"{missing_pins} pins are not loose on page 1 or in the dock.")
    if not diagnoses:
        diagnoses.append("A compact layout. No clear issues.")
    return Score(max(0, 100 - sum(penalties.values())), penalties, diagnoses[:4], counts=counts)
