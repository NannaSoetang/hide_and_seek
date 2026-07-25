"""Build static municipality boundaries for the interactive map.

Source: Dataforsyningen kommuner GeoJSON endpoint.
The frontend consumes only local static output from web/public/data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PUBLIC_DATA = ROOT / "web" / "public" / "data"
BOUNDARY_PATH = PUBLIC_DATA / "boundary.geojson"
RAW_KOMMUNER_PATH = RAW_DIR / "kommuner.geojson"
OUTPUT_PATH = PUBLIC_DATA / "municipalities.geojson"
KOMMUNER_URL = "https://api.dataforsyningen.dk/kommuner?format=geojson"
SIMPLIFY_TOLERANCE = 0.00008


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)


def load_geojson(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_geojson(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def fetch_kommuner() -> dict[str, Any]:
    response = requests.get(KOMMUNER_URL, timeout=120)
    response.raise_for_status()
    payload = response.json()
    write_geojson(RAW_KOMMUNER_PATH, payload)
    return payload


def get_boundary_shape() -> Any:
    if not BOUNDARY_PATH.exists():
        raise FileNotFoundError(
            f"Missing boundary dataset at {BOUNDARY_PATH}. Build base map data first."
        )
    boundary = load_geojson(BOUNDARY_PATH)
    feature = (boundary.get("features") or [None])[0]
    if not feature:
        raise RuntimeError("Boundary GeoJSON does not contain a feature")
    return shape(feature["geometry"])


def municipality_name(properties: dict[str, Any]) -> str:
    for key in ("navn", "name", "kommunenavn", "KOMMUNENAVN"):
        value = properties.get(key)
        if value:
            return str(value)
    return "Ukendt kommune"


def municipality_code(properties: dict[str, Any]) -> str:
    for key in ("kode", "kommunekode", "kommunenr", "KOMMUNEKODE"):
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return "-"


def build_municipalities(boundary_shape: Any, kommuner: dict[str, Any]) -> dict[str, Any]:
    features = []
    for feature in kommuner.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        kommune_shape = shape(geometry)
        if not kommune_shape.intersects(boundary_shape):
            continue
        clipped = kommune_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue
        simplified = clipped.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        properties = feature.get("properties") or {}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": municipality_name(properties),
                    "code": municipality_code(properties),
                    "source": "Dataforsyningen kommuner",
                },
                "geometry": mapping(simplified),
            }
        )

    features.sort(key=lambda item: item["properties"]["name"])
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    ensure_dirs()
    boundary_shape = get_boundary_shape()
    kommuner = fetch_kommuner()
    municipalities = build_municipalities(boundary_shape, kommuner)
    write_geojson(OUTPUT_PATH, municipalities)
    print(f"Wrote {len(municipalities['features'])} municipalities to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
