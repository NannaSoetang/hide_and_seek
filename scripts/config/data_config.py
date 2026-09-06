"""Configuration and source definitions for the dataset build pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PUBLIC_DIR = ROOT / "web" / "public" / "data"
TRANSIT_RULES_PATH = ROOT / "scripts" / "config" / "transit_rules.yaml"
GTFS_URL = "https://www.rejseplanen.info/labs/GTFS.zip"
GTFS_ZIP = RAW_DIR / "gtfs.zip"
MOVIA_ZONES_URL = "https://geoservices.moviatrafik.dk/arcgis/rest/services/WebGIS/bus_webGIS/MapServer/6/query?where=1%3D1&outFields=*&returnGeometry=true&f=geojson"
MOVIA_ZONES_GEOJSON = RAW_DIR / "movia_zones.geojson"
KOMMUNER_GEOJSON = RAW_DIR / "kommuner.geojson"
POSTNUMRE_GEOJSON = RAW_DIR / "postnumre.geojson"
OPSTILLINGSKREDSE_GEOJSON = RAW_DIR / "opstillingskredse.geojson"
SOGNE_GEOJSON = RAW_DIR / "sogne.geojson"
KOMMUNER_URL = "https://api.dataforsyningen.dk/kommuner?format=geojson"
POSTNUMRE_URL = "https://api.dataforsyningen.dk/postnumre?format=geojson"
OPSTILLINGSKREDSE_URL = "https://api.dataforsyningen.dk/opstillingskredse?format=geojson"
SOGNE_URL = "https://api.dataforsyningen.dk/sogne?format=geojson"
ADMIN_SIMPLIFY_TOLERANCE = {
    "municipalities": 0.00008,
    "postnumre": 0.00012,
    "opstillingskredse": 0.00010,
    "sogne": 0.00008,
}


def _parse_simple_yaml_config(text: str) -> dict[str, Any]:
    config: dict[str, Any] = {"service": {}, "transit": [], "zones": []}
    current_section: str | None = None
    current_rule: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"(service|transit|zones):", line):
            current_section = line[:-1]
            current_rule = None
            continue
        if current_section == "service" and ":" in line:
            key, value = line.split(":", 1)
            config["service"][key.strip()] = value.strip().strip('"\'')
            continue
        if current_section == "transit" and line.startswith("- "):
            remainder = line[2:].strip()
            current_rule = {}
            if ":" in remainder:
                key, value = remainder.split(":", 1)
                current_rule[key.strip()] = value.strip().strip('"\'')
            else:
                current_rule["type"] = remainder.strip().strip('"\'')
            config["transit"].append(current_rule)
            continue
        if current_section == "transit" and current_rule is not None and ":" in line:
            key, value = line.split(":", 1)
            current_rule[key.strip()] = value.strip().strip('"\'')
            continue
        if current_section == "zones" and line.startswith("- "):
            config["zones"].append(line[2:].strip().strip('"\''))

    return config


def load_transit_config(path: Path | None = None) -> dict[str, Any]:
    candidate = Path(path) if path is not None else TRANSIT_RULES_PATH
    if not candidate.exists():
        raise FileNotFoundError(f"Transit rules config is required: {candidate}")

    config = _parse_simple_yaml_config(candidate.read_text(encoding="utf-8"))
    rules = [
        {str(key): str(value) for key, value in entry.items() if key in {"type", "pattern"} and value is not None}
        for entry in config["transit"]
    ]
    rules = [rule for rule in rules if rule]
    service = config.get("service", {})
    if service:
        service = {str(key): str(value).strip() for key, value in service.items() if str(value).strip()}

    return {
        "transit": rules,
        "service": service,
        "zones": [str(zone).strip() for zone in config.get("zones", []) if str(zone).strip()],
    }


def load_transit_rules(path: Path | None = None) -> list[dict[str, str]]:
    return load_transit_config(path).get("transit", [])


DEFAULT_TRANSIT_CONFIG = load_transit_config()
DEFAULT_TRANSIT_SELECTION_RULES: list[dict[str, str]] = DEFAULT_TRANSIT_CONFIG["transit"]
DEFAULT_TRANSIT_SERVICE: dict[str, str] = DEFAULT_TRANSIT_CONFIG.get("service", {})
DEFAULT_TRANSIT_ZONES: set[str] = set(DEFAULT_TRANSIT_CONFIG["zones"])
