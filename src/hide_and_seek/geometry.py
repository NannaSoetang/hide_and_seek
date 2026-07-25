"""Small geometry helpers for the preprocessing pipeline."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Point, mapping, shape


# TODO: `RANDERS_CENTER` is a Randers-specific fallback. Make this configurable
# or compute a region centroid dynamically when the project targets a different
# area (e.g. Storkøbenhavn).
RANDERS_CENTER = (10.03639, 56.4607)
PROVISIONAL_RADIUS_KM = 20.0


def distance_km(
    lon: float, lat: float, center: tuple[float, float] = RANDERS_CENTER
) -> float:
    """Return approximate great-circle distance in kilometers."""
    lon1, lat1 = map(math.radians, center)
    lon2, lat2 = math.radians(lon), math.radians(lat)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def within_provisional_area(lon: float, lat: float) -> bool:
    """Return whether a coordinate lies inside the provisional first-pass area."""
    return distance_km(lon, lat) <= PROVISIONAL_RADIUS_KM


def make_provisional_boundary_feature() -> dict[str, Any]:
    """Return a GeoJSON feature for the provisional work area."""
    center = Point(RANDERS_CENTER)
    radius_deg = PROVISIONAL_RADIUS_KM / 111.0
    polygon = center.buffer(radius_deg, resolution=128)
    return {
        "type": "Feature",
        "properties": {
            "name": "Midlertidigt arbejdsomraade",
            "note": "Dette er en forelobig cirkel omkring Randers centrum. Den officielle 2006-graense mangler stadig.",
            "radius_km": PROVISIONAL_RADIUS_KM,
        },
        "geometry": mapping(polygon),
    }


def intersects_provisional_area(feature_geometry: dict[str, Any]) -> bool:
    """Return whether a feature geometry intersects the provisional work area."""
    boundary = shape(make_provisional_boundary_feature()["geometry"])
    return shape(feature_geometry).intersects(boundary)
