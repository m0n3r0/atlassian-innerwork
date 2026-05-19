from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json_resource(relative_path: str) -> dict[str, Any]:
    """Load repo data in editable installs and from packaged wheels."""

    repo_path = _repo_root() / relative_path
    if repo_path.exists():
        return json.loads(repo_path.read_text(encoding="utf-8"))

    package_path = relative_path.replace("/", ".")
    top_level, _, name = package_path.partition(".")
    if top_level != "data" or not name.endswith("json"):
        raise FileNotFoundError(relative_path)
    with resources.files("innerwork.data").joinpath(name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def product_catalog() -> dict[str, Any]:
    return load_json_resource("data/product_catalog.json")


@lru_cache(maxsize=1)
def production_oss_phases() -> dict[str, Any]:
    return load_json_resource("data/production_oss_phases.json")


def broker_catalog() -> dict[str, Any]:
    """Return an OSB-shaped catalog generated from public product metadata."""

    catalog = product_catalog()
    profiles = catalog["edge_profiles"]
    profile_plans = [
        {
            "id": profile,
            "name": profile.replace("_", " ").title(),
            "description": "Intent profile rendered by the Innerwork control plane.",
        }
        for profile in profiles
    ]
    return {
        "services": [
            {
                "id": "innerwork-edge-service",
                "name": "Innerwork Edge Service",
                "description": "Self-service domain, route, and edge-filter brokerage.",
                "plans": profile_plans,
            }
        ]
    }
