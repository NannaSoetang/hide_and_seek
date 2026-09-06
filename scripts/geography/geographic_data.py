"""Geographic source loading and administrative GeoJSON builders."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

from scripts.config.data_config import (
    ADMIN_SIMPLIFY_TOLERANCE,
    KOMMUNER_GEOJSON,
    KOMMUNER_URL,
    OPSTILLINGSKREDSE_GEOJSON,
    OPSTILLINGSKREDSE_URL,
    POSTNUMRE_GEOJSON,
    POSTNUMRE_URL,
    PUBLIC_DIR,
    SOGNE_GEOJSON,
    SOGNE_URL,
)
from scripts.io.data_io import download_if_missing


def load_region_boundary_feature(public_dir: Path = PUBLIC_DIR) -> dict[str, Any]:
    boundary_path = public_dir / "boundary.geojson"
    collection = json.loads(boundary_path.read_text())
    feature = (collection.get("features") or [None])[0]
    if not feature:
        raise RuntimeError(f"Boundary GeoJSON contains no feature: {boundary_path}")
    return feature


def load_movia_zone_shapes(
    boundary_shape: Any,
    allowed_names: set[str],
    source_path: Path,
    source_url: str,
    downloader: Callable[[str, Path], None] = download_if_missing,
) -> list[Any]:
    downloader(source_url, source_path)
    source = json.loads(source_path.read_text())
    features = source.get("features", [])
    if not features:
        return []

    def first_coord(feature: dict) -> tuple[float, float] | None:
        coords = (feature.get("geometry") or {}).get("coordinates")
        if not coords:
            return None
        current = coords
        while isinstance(current, list) and current and isinstance(current[0], list):
            current = current[0]
        if isinstance(current, list) and len(current) >= 2 and isinstance(current[0], (int, float)):
            return current[0], current[1]
        return None

    first = first_coord(features[0])
    transformer = None
    if first and (abs(first[0]) > 1000 or abs(first[1]) > 1000):
        transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)

    zone_shapes: list[Any] = []
    found_names: set[str] = set()
    for feature in features:
        props = feature.get("properties", {}) or {}
        raw_name = str(props.get("Name") or props.get("NAME") or props.get("name") or "").strip()
        numbers = re.findall(r"\d+", raw_name)
        name = (numbers[0].lstrip("0") or "0") if numbers else raw_name
        if name not in allowed_names:
            continue
        found_names.add(name)
        geometry = feature.get("geometry")
        if not geometry:
            continue
        zone_shape = shape(geometry)
        if transformer is not None:
            zone_shape = shapely_transform(lambda x, y: transformer.transform(x, y), zone_shape)
        if not zone_shape.intersects(boundary_shape):
            continue
        clipped = zone_shape.intersection(boundary_shape)
        if not clipped.is_empty:
            zone_shapes.append(clipped)

    missing_names = allowed_names - found_names
    if missing_names:
        raise RuntimeError(f"Configured Movia zones were not found: {', '.join(sorted(missing_names))}")
    if not zone_shapes:
        raise RuntimeError("Configured Movia zones do not overlap the game boundary")
    return zone_shapes


def build_admin_dataset(
    source: dict[str, Any],
    boundary_shape: Any,
    simplify_tolerance: float,
    properties_builder: Callable[[dict[str, Any]], dict[str, str]],
    sort_key,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for feature in source.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        raw_shape = shape(geometry)
        if not raw_shape.intersects(boundary_shape):
            continue
        clipped = raw_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue
        simplified = clipped.simplify(simplify_tolerance, preserve_topology=True)
        if simplified.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": properties_builder(feature.get("properties", {}) or {}),
            "geometry": mapping(simplified),
        })
    features.sort(key=sort_key)
    return {"type": "FeatureCollection", "features": features}


def build_sogne_dataset(boundary_feature: dict[str, Any], downloader=download_if_missing) -> dict[str, Any]:
    downloader(SOGNE_URL, SOGNE_GEOJSON)
    source = json.loads(SOGNE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["sogne"],
        lambda props: {
            "name": props["navn"],
            "code": props["kode"],
            "source": "Dataforsyningen sogne",
        },
        sort_key=lambda feature: feature["properties"]["name"],
    )


def build_municipalities_dataset(boundary_feature: dict[str, Any], downloader=download_if_missing) -> dict[str, Any]:
    downloader(KOMMUNER_URL, KOMMUNER_GEOJSON)
    source = json.loads(KOMMUNER_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["municipalities"],
        lambda props: {
            "name": props["navn"],
            "code": props["kode"],
            "source": "Dataforsyningen kommuner",
        },
        sort_key=lambda feature: feature["properties"]["name"],
    )


def build_postnumre_dataset(boundary_feature: dict[str, Any], downloader=download_if_missing) -> dict[str, Any]:
    downloader(POSTNUMRE_URL, POSTNUMRE_GEOJSON)
    source = json.loads(POSTNUMRE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    grouped_geometries: dict[str, list[Any]] = {}
    for feature in source.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        raw_shape = shape(geometry)
        if not raw_shape.intersects(boundary_shape):
            continue
        clipped = raw_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue
        props = feature.get("properties", {}) or {}
        label = props["navn"]
        grouped_geometries.setdefault(label, []).append(clipped)

    features = []
    for label, geometries in grouped_geometries.items():
        simplified = unary_union(geometries).simplify(ADMIN_SIMPLIFY_TOLERANCE["postnumre"], preserve_topology=True)
        if simplified.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": {"postnummernavn": label, "source": "Dataforsyningen postnumre"},
            "geometry": mapping(simplified),
        })
    features.sort(key=lambda feature: feature["properties"]["postnummernavn"])
    return {"type": "FeatureCollection", "features": features}


def build_opstillingskredse_dataset(boundary_feature: dict[str, Any], downloader=download_if_missing) -> dict[str, Any]:
    downloader(OPSTILLINGSKREDSE_URL, OPSTILLINGSKREDSE_GEOJSON)
    source = json.loads(OPSTILLINGSKREDSE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["opstillingskredse"],
        lambda props: {
            "name": props["navn"],
            "number": props["nummer"],
            "source": "Dataforsyningen opstillingskredse",
        },
        sort_key=lambda feature: (feature["properties"]["name"], feature["properties"]["number"]),
    )
