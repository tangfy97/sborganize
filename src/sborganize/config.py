import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    pins: tuple[str, ...] = ()
    new_folder_min_apps: int = 3
    target_pages: int = 3
    folder_page_size: int = 9
    folders: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    create_folders: bool = True
    compact_folders: bool = True
    regions: dict[str, str] = field(default_factory=dict)
    region_folders: dict[str, str] = field(default_factory=dict)
    openrouter_model: str = "qwen/qwen3.5-flash-02-23"


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    for section in ("planner", "pins", "folders", "smart"):
        if not isinstance(data.get(section, {}), dict):
            raise ValueError(f"{section} must be a TOML table.")
    planner = data.get("planner", {})
    values = {}
    for key, default, minimum in (
        ("new_folder_min_apps", 3, 2),
        ("target_pages", 3, 1),
        ("folder_page_size", 9, 1),
    ):
        value = planner.get(key, default)
        if type(value) is not int or not minimum <= value <= 100:
            raise ValueError(f"planner.{key} must be an integer from {minimum} to 100.")
        values[key] = value
    pins = data.get("pins", {}).get("bundle_ids", [])
    if not isinstance(pins, list) or not all(isinstance(p, str) for p in pins):
        raise ValueError("pins.bundle_ids must be a list of bundle IDs.")
    folders = data.get("folders", {}).get("map", {})
    categories = data.get("categories", {})
    regions = data.get("regions", {})
    region_folders = data.get("folders", {}).get("regions", {})
    for name, mapping in (
        ("folders.map", folders),
        ("categories", categories),
        ("regions", regions),
        ("folders.regions", region_folders),
    ):
        if not isinstance(mapping, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in mapping.items()
        ):
            raise ValueError(f"{name} must map strings to nonempty strings.")
    if any(value not in ("CN", "HK", "GLOBAL") for value in regions.values()):
        raise ValueError("regions values must be CN, HK or GLOBAL.")
    if any(key not in ("CN", "HK") for key in region_folders):
        raise ValueError("folders.regions keys must be CN or HK.")
    targets = {"CN": "🇨🇳", "HK": "HK", **region_folders}
    if targets["CN"].casefold() == targets["HK"].casefold():
        raise ValueError("CN and HK must use separate folders.")
    cloud_model = data.get("smart", {}).get("openrouter_model", "qwen/qwen3.5-flash-02-23")
    if not isinstance(cloud_model, str) or not cloud_model.strip() or len(cloud_model) > 200:
        raise ValueError("smart.openrouter_model must be a model identifier.")
    if planner.get("preserve_dock", True) is not True:
        raise ValueError("This prototype always preserves the dock; remove preserve_dock=false.")
    policies = {}
    for key in ("create_folders", "compact_folders"):
        policies[key] = planner.get(key, True)
        if type(policies[key]) is not bool:
            raise ValueError(f"planner.{key} must be true or false.")
    return Config(
        pins=tuple(pins),
        folders=folders,
        categories=categories,
        regions=regions,
        region_folders=region_folders,
        openrouter_model=cloud_model,
        **policies,
        **values,
    )
