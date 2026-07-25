"""Build a first-pass static dataset for the web app and printable map.

This intentionally ships a provisional work area while the official 2006 Randers
municipality boundary remains unresolved in this environment.

TODO: Replace Randers-specific references and workflows with a configurable
region (e.g. Storkøbenhavn). See `KOMMUNEKODER` in this module for guidance.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import unary_union

# geometry utilities are available in `hide_and_seek.geometry` if needed.
from hide_and_seek.rules import (
    MIN_TOTAL_EVENTS,
    has_consecutive_eligible_stops,
    is_stop_eligible,
    is_time_in_window,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"
PUBLIC_DIR = ROOT / "web" / "public" / "data"
GTFS_URL = "https://www.rejseplanen.info/labs/GTFS.zip"
GTFS_ZIP = RAW_DIR / "gtfs.zip"
KOMMUNER_GEOJSON = RAW_DIR / "kommuner.geojson"
POSTNUMRE_GEOJSON = RAW_DIR / "postnumre.geojson"
OPSTILLINGSKREDSE_GEOJSON = RAW_DIR / "opstillingskredse.geojson"
SOGNE_GEOJSON = RAW_DIR / "sogne.geojson"
AFSTEMNINGSOMRAADER_GEOJSON = RAW_DIR / "afstemningsomraader.geojson"
KOMMUNER_PREREFORM = RAW_DIR / "kommuner-pre-strukturreform-geojson-wgs84.geojson"
KOMMUNER_URL = "https://api.dataforsyningen.dk/kommuner?format=geojson"
POSTNUMRE_URL = "https://api.dataforsyningen.dk/postnumre?format=geojson"
OPSTILLINGSKREDSE_URL = "https://api.dataforsyningen.dk/opstillingskredse?format=geojson"
SOGNE_URL = "https://api.dataforsyningen.dk/sogne?format=geojson"
KOMMUNEKODER = [
    "0101",  # København
    "0147",  # Frederiksberg
    "0151",  # Ballerup
    "0153",  # Brøndby
    "0155",  # Dragør
    "0157",  # Gentofte
    "0159",  # Gladsaxe
    "0161",  # Glostrup
    "0163",  # Herlev
    "0165",  # Albertslund
    "0167",  # Hvidovre
    "0169",  # Høje-Taastrup
    "0173",  # Lyngby-Taarbæk
    "0175",  # Rødovre
    "0183",  # Ishøj
    "0185",  # Tårnby
    "0187",  # Vallensbæk
    "0190",  # Furesø
    "0201",  # Allerød
    "0219",  # Hillerød
    "0223",  # Hørsholm
    "0230",  # Rudersdal
    "0240",  # Egedal
    "0250",  # Frederikssund
    "0253",  # Greve
    "0259",  # Køge
    "0265",  # Roskilde
    "0269",  # Solrød
]

AFSTEMNINGSOMRAADER_URL = (
    "https://api.dataforsyningen.dk/afstemningsomraader"
)
NEARBY_RADIUS_METERS = 750
REQUIRED_HOURS = tuple(range(9, 18))
ADMIN_SIMPLIFY_TOLERANCE = {
    "municipalities": 0.00008,
    "postnumre": 0.00012,
    "opstillingskredse": 0.00010,
    "sogne": 0.00008,
}


@dataclass
class Stop:
    stop_id: str
    name: str
    lat: float
    lon: float


WGS84_TO_ETRS89_UTM32 = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def download_if_missing(url: str, destination: Path) -> None:
    """Download a file only when it is not already present."""
    if destination.exists():
        return
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)


def load_csv_from_zip(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    """Read a smaller CSV file from a GTFS ZIP archive."""
    with archive.open(name) as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))


def iter_csv_from_zip(archive: zipfile.ZipFile, name: str):
    """Yield CSV rows from a GTFS ZIP archive without materializing the full file."""
    with archive.open(name) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))


def load_region_boundary_feature() -> dict[str, Any]:
    """Build a single region boundary by unioning kommune geometries for
    the codes listed in `KOMMUNEKODER` from the pre-reform kommuner GeoJSON.
    """
    fallback_boundary = PUBLIC_DIR / "boundary.geojson"
    if not KOMMUNER_PREREFORM.exists() and fallback_boundary.exists():
        fallback = json.loads(fallback_boundary.read_text())
        feature = (fallback.get("features") or [None])[0]
        if feature:
            return feature

    collection = json.loads(KOMMUNER_PREREFORM.read_text())
    matched = []
    for feature in collection.get("features", []):
        props = feature.get("properties", {}) or {}
        # Try a few common property names where a kommune-kode might appear.
        kode_candidates = [
            props.get("kode"),
            props.get("kommunekode"),
            props.get("kommunenr"),
            props.get("KOMMUNEKODE"),
        ]
        # Also try to find the code among any string-ish property values.
        for v in props.values():
            if isinstance(v, str) and v.isdigit() and len(v) == 4:
                kode_candidates.append(v)

        if any(k in KOMMUNEKODER for k in (c for c in kode_candidates if c)):
            matched.append(feature)

    if not matched:
        raise RuntimeError("No kommuner matched KOMMUNEKODER in the pre-reform file")

    # Union all matched kommune geometries into a single geometry for the region.
    shapes = [shape(f["geometry"]) for f in matched]
    unioned = unary_union(shapes)
    return {
        "type": "Feature",
        "properties": {
            "name": "Storkøbenhavn",
            "note": "Union of kommuner for Storkøbenhavn built from pre-reform GeoJSON.",
            "kommunekoder": KOMMUNEKODER,
        },
        "geometry": mapping(unioned),
    }


def build_transit_dataset(
    boundary_feature: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create route, stop, and summary datasets from GTFS."""
    boundary_shape = shape(boundary_feature["geometry"])
    route_view_shape = boundary_shape
    # Compute a sensible map center from the provided region boundary.
    region_centroid = boundary_shape.centroid.coords[0]

    with zipfile.ZipFile(GTFS_ZIP) as archive:
        stops_rows = load_csv_from_zip(archive, "stops.txt")
        routes_rows = load_csv_from_zip(archive, "routes.txt")
        trips_rows = load_csv_from_zip(archive, "trips.txt")
        calendar_rows = load_csv_from_zip(archive, "calendar.txt")
        bus_route_ids = {
            row["route_id"]
            for row in routes_rows
            if row.get("route_type") in {"3", "700"}
        }
        saturday_service_ids = {
            row["service_id"] for row in calendar_rows if row.get("saturday") == "1"
        }
    relevant_trips = {
        row["trip_id"]: row
        for row in trips_rows
        if row.get("route_id") in bus_route_ids
        and row.get("service_id") in saturday_service_ids
    }
    all_route_shape_ids: dict[str, set[str]] = defaultdict(set)
    for trip in relevant_trips.values():
        if trip.get("shape_id"):
            all_route_shape_ids[trip["route_id"]].add(trip["shape_id"])

    stops = {
        row["stop_id"]: Stop(
            stop_id=row["stop_id"],
            name=row.get("stop_name", row["stop_id"]),
            lat=float(row["stop_lat"]),
            lon=float(row["stop_lon"]),
        )
        for row in stops_rows
        if row.get("location_type", "0") in {"", "0"}
    }
    area_stop_ids = {
        stop_id
        for stop_id, stop in stops.items()
        if boundary_shape.contains(
            shape({"type": "Point", "coordinates": [stop.lon, stop.lat]})
        )
    }

    stop_event_counts: Counter[str] = Counter()
    stop_hour_counts: dict[str, Counter[int]] = defaultdict(Counter)
    trip_area_sequences: dict[str, list[tuple[int, str]]] = defaultdict(list)

    with zipfile.ZipFile(GTFS_ZIP) as archive:
        for row in iter_csv_from_zip(archive, "stop_times.txt"):
            trip_id = row.get("trip_id")
            if trip_id not in relevant_trips:
                continue
            stop_id = row.get("stop_id")
            if stop_id not in area_stop_ids:
                continue
            if is_time_in_window(
                row.get("departure_time") or row.get("arrival_time") or ""
            ):
                service_hour = int(
                    (
                        row.get("departure_time")
                        or row.get("arrival_time")
                        or "0:00:00"
                    ).split(":", 1)[0]
                )
                stop_event_counts[stop_id] += 1
                stop_hour_counts[stop_id][service_hour] += 1
            trip_area_sequences[trip_id].append(
                (int(row.get("stop_sequence") or 0), stop_id)
            )

    area_stop_list = sorted(stop_event_counts)
    projected_stops = {
        stop_id: WGS84_TO_ETRS89_UTM32.transform(stops[stop_id].lon, stops[stop_id].lat)
        for stop_id in area_stop_list
    }
    nearby_event_counts: dict[str, int] = {}
    for stop_id in area_stop_list:
        x1, y1 = projected_stops[stop_id]
        nearby_total = 0
        for other_stop_id in area_stop_list:
            x2, y2 = projected_stops[other_stop_id]
            if (x1 - x2) ** 2 + (y1 - y2) ** 2 <= NEARBY_RADIUS_METERS**2:
                nearby_total += stop_event_counts[other_stop_id]
        nearby_event_counts[stop_id] = nearby_total

    eligible_stop_ids = {
        stop_id
        for stop_id, count in nearby_event_counts.items()
        if is_stop_eligible(count)
        and all(stop_hour_counts[stop_id][hour] >= 1 for hour in REQUIRED_HOURS)
    }
    route_has_eligible_sequence: dict[str, bool] = defaultdict(bool)
    route_shape_ids: dict[str, set[str]] = defaultdict(set)

    for trip_id, sequence_rows in trip_area_sequences.items():
        trip = relevant_trips[trip_id]
        ordered_stop_ids = [stop_id for _, stop_id in sorted(sequence_rows)]
        route_id = trip["route_id"]
        if has_consecutive_eligible_stops(ordered_stop_ids, eligible_stop_ids):
            route_has_eligible_sequence[route_id] = True
            if trip.get("shape_id"):
                route_shape_ids[route_id].add(trip["shape_id"])

    included_route_ids = {
        route_id for route_id, ok in route_has_eligible_sequence.items() if ok
    }
    route_by_id = {row["route_id"]: row for row in routes_rows}
    selected_shape_ids = {
        shape_id
        for route_id in included_route_ids
        for shape_id in all_route_shape_ids[route_id]
    }

    shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    with zipfile.ZipFile(GTFS_ZIP) as archive:
        for row in iter_csv_from_zip(archive, "shapes.txt"):
            shape_id = row.get("shape_id")
            if not shape_id or shape_id not in selected_shape_ids:
                continue
            shape_points[shape_id].append(
                (
                    int(row.get("shape_pt_sequence") or 0),
                    float(row["shape_pt_lon"]),
                    float(row["shape_pt_lat"]),
                )
            )

    route_features = []
    for route_id in sorted(included_route_ids):
        route = route_by_id[route_id]
        route_geometries = []
        for shape_id in sorted(all_route_shape_ids[route_id]):
            if shape_id not in shape_points:
                continue
            coords = [(lon, lat) for _, lon, lat in sorted(shape_points[shape_id])]
            clipped_geometry = LineString(coords).intersection(route_view_shape)
            if clipped_geometry.is_empty:
                continue
            route_geometries.append(clipped_geometry)

        if not route_geometries:
            continue

        line_parts = []
        for route_geometry in route_geometries:
            if route_geometry.geom_type == "LineString":
                line_parts.append(list(route_geometry.coords))
            elif route_geometry.geom_type == "MultiLineString":
                line_parts.extend(list(part.coords) for part in route_geometry.geoms)

        if not line_parts:
            continue

        geometry = mapping(
            route_geometries[0] if len(line_parts) == 1 else MultiLineString(line_parts)
        )
        route_features.append(
            {
                "type": "Feature",
                "properties": {
                    "route_id": route_id,
                    "label": route.get("route_short_name")
                    or route.get("route_long_name")
                    or route_id,
                    "name": route.get("route_long_name")
                    or route.get("route_short_name")
                    or route_id,
                    "agency_id": route.get("agency_id"),
                },
                "geometry": geometry,
            }
        )

    major_stop_ids = {
        stop_id
        for stop_id, _ in sorted(
            nearby_event_counts.items(), key=lambda item: item[1], reverse=True
        )[:15]
        if stop_id in eligible_stop_ids
    }

    stop_features = []
    for stop_id in sorted(eligible_stop_ids):
        stop = stops[stop_id]
        stop_features.append(
            {
                "type": "Feature",
                "properties": {
                    "stop_id": stop_id,
                    "name": stop.name,
                    "events": stop_event_counts[stop_id],
                    "nearby_events": nearby_event_counts[stop_id],
                    "major": stop_id in major_stop_ids,
                },
                "geometry": {"type": "Point", "coordinates": [stop.lon, stop.lat]},
            }
        )

    metadata = {
        "center": {"lon": region_centroid[0], "lat": region_centroid[1]},
        "boundary_status": "official-pre-reform",
        "boundary_note": "Regionens grænse er konstrueret fra pre-reform kommunefiler.",
        "eligible_stop_count": len(stop_features),
        "included_route_count": len(route_features),
        "play_window": "09:00-18:00 normal lordag",
        "eligibility_rule": f"Stop er gyldigt hvis stop inden for {NEARBY_RADIUS_METERS} meter tilsammen har mindst {MIN_TOTAL_EVENTS} bushaendelser i spilvinduet, og stoppet selv har mindst en direkte bushaendelse i hver time fra 09 til 17.",
        "nearby_radius_meters": NEARBY_RADIUS_METERS,
    }

    return (
        {"type": "FeatureCollection", "features": route_features},
        {"type": "FeatureCollection", "features": stop_features},
        metadata,
    )


def build_sogne_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized sogne dataset clipped to the game boundary."""
    download_if_missing(SOGNE_URL, SOGNE_GEOJSON)
    source = json.loads(SOGNE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["sogne"],
        lambda props: {
            "name": _first_non_empty(
                props,
                "navn",
                "name",
                "sognenavn",
                "SOGNENAVN",
            )
            or "Ukendt sogn",
            "code": _first_non_empty(
                props,
                "sognekode",
                "kode",
                "sognenr",
                "SOGNEKODE",
            )
            or "-",
            "source": "Dataforsyningen sogne",
        },
        sort_key=lambda feat: feat["properties"]["name"],
    )


def _first_non_empty(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _build_admin_dataset(
    source: dict[str, Any],
    boundary_shape: Any,
    simplify_tolerance: float,
    properties_builder,
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

        props = feature.get("properties", {}) or {}
        features.append(
            {
                "type": "Feature",
                "properties": properties_builder(props),
                "geometry": mapping(simplified),
            }
        )

    features.sort(key=sort_key)
    return {"type": "FeatureCollection", "features": features}


def build_municipalities_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized kommune boundaries from the official dataset."""
    download_if_missing(KOMMUNER_URL, KOMMUNER_GEOJSON)
    source = json.loads(KOMMUNER_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["municipalities"],
        lambda props: {
            "name": _first_non_empty(props, "navn", "name", "kommunenavn", "KOMMUNENAVN")
            or "Ukendt kommune",
            "code": _first_non_empty(props, "kode", "kommunekode", "kommunenr", "KOMMUNEKODE")
            or "-",
            "source": "Dataforsyningen kommuner",
        },
        sort_key=lambda feat: feat["properties"]["name"],
    )


def build_postnumre_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized postområde boundaries grouped by postnummernavn."""
    download_if_missing(POSTNUMRE_URL, POSTNUMRE_GEOJSON)
    source = json.loads(POSTNUMRE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    grouped_geometries: dict[str, list[Any]] = defaultdict(list)
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
        label = _first_non_empty(props, "navn", "postnrnavn", "postnummernavn")
        if not label:
            label = "Ukendt postområde"
        grouped_geometries[label].append(clipped)

    features: list[dict[str, Any]] = []
    for label, geometries in grouped_geometries.items():
        merged = unary_union(geometries)
        simplified = merged.simplify(ADMIN_SIMPLIFY_TOLERANCE["postnumre"], preserve_topology=True)
        if simplified.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "postnummernavn": label,
                    "source": "Dataforsyningen postnumre",
                },
                "geometry": mapping(simplified),
            }
        )

    features.sort(key=lambda feat: feat["properties"]["postnummernavn"])
    return {"type": "FeatureCollection", "features": features}


def build_opstillingskredse_dataset(boundary_feature: dict[str, Any]) -> dict[str, Any]:
    """Build normalized opstillingskredse boundaries."""
    download_if_missing(OPSTILLINGSKREDSE_URL, OPSTILLINGSKREDSE_GEOJSON)
    source = json.loads(OPSTILLINGSKREDSE_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    return _build_admin_dataset(
        source,
        boundary_shape,
        ADMIN_SIMPLIFY_TOLERANCE["opstillingskredse"],
        lambda props: {
            "name": _first_non_empty(props, "navn", "name", "opstillingskredsnavn")
            or "Ukendt opstillingskreds",
            "number": _first_non_empty(props, "nummer", "nr", "opstillingskredsnummer")
            or "-",
            "source": "Dataforsyningen opstillingskredse",
        },
        sort_key=lambda feat: (feat["properties"]["name"], feat["properties"]["number"]),
    )


def _feature_has_kommunekode(feature: dict[str, Any], codes: list[str]) -> bool:
    props = feature.get("properties", {}) or {}
    # Direct properties commonly used by Dataforsyningen
    if any(props.get(k) in codes for k in ("kommunekode", "kode", "KOMMUNEKODE")):
        return True
    # Sometimes kommune info is nested or encoded in other props.
    for v in props.values():
        if isinstance(v, str) and v in codes:
            return True
        if isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, dict) and any(
                    str(item.get(k)) in codes for k in ("kode", "kommunekode", "KOMMUNEKODE")
                ):
                    return True
    return False


def build_afstemningsomraader_dataset(
    boundary_feature: dict[str, Any],
) -> dict[str, Any]:
    """Download all afstemningsområder once, then filter to the desired
    Storkøbenhavn kommuner and the region boundary.
    """
    download_if_missing(AFSTEMNINGSOMRAADER_URL + "?format=geojson", AFSTEMNINGSOMRAADER_GEOJSON)
    all_areas = json.loads(AFSTEMNINGSOMRAADER_GEOJSON.read_text())
    boundary_shape = shape(boundary_feature["geometry"])
    filtered = []
    for feature in all_areas.get("features", []):
        # Prefer filtering by kommune code first (fast), then by geometry.
        if _feature_has_kommunekode(feature, KOMMUNEKODER) or shape(feature["geometry"]).intersects(boundary_shape):
            filtered.append(feature)
    return {"type": "FeatureCollection", "features": filtered}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def main() -> None:
    """Build all first-pass derived data files."""
    ensure_dirs()
    download_if_missing(GTFS_URL, GTFS_ZIP)
    boundary_feature = load_region_boundary_feature()
    routes, stops, metadata = build_transit_dataset(boundary_feature)
    municipalities = build_municipalities_dataset(boundary_feature)
    postnumre = build_postnumre_dataset(boundary_feature)
    opstillingskredse = build_opstillingskredse_dataset(boundary_feature)
    sogne = build_sogne_dataset(boundary_feature)
    afstemningsomraader = build_afstemningsomraader_dataset(boundary_feature)
    boundary = {
        "type": "FeatureCollection",
        "features": [boundary_feature],
    }

    write_json(DERIVED_DIR / "routes.geojson", routes)
    write_json(DERIVED_DIR / "eligible-stops.geojson", stops)
    write_json(DERIVED_DIR / "municipalities.geojson", municipalities)
    write_json(DERIVED_DIR / "postnumre.geojson", postnumre)
    write_json(DERIVED_DIR / "opstillingskredse.geojson", opstillingskredse)
    write_json(DERIVED_DIR / "sogne.geojson", sogne)
    write_json(DERIVED_DIR / "afstemningsomraader.geojson", afstemningsomraader)
    write_json(DERIVED_DIR / "boundary.geojson", boundary)
    write_json(DERIVED_DIR / "metadata.json", metadata)

    write_json(PUBLIC_DIR / "routes.geojson", routes)
    write_json(PUBLIC_DIR / "eligible-stops.geojson", stops)
    write_json(PUBLIC_DIR / "municipalities.geojson", municipalities)
    write_json(PUBLIC_DIR / "postnumre.geojson", postnumre)
    write_json(PUBLIC_DIR / "opstillingskredse.geojson", opstillingskredse)
    write_json(PUBLIC_DIR / "sogne.geojson", sogne)
    write_json(PUBLIC_DIR / "afstemningsomraader.geojson", afstemningsomraader)
    write_json(PUBLIC_DIR / "boundary.geojson", boundary)
    write_json(PUBLIC_DIR / "metadata.json", metadata)


if __name__ == "__main__":
    main()
