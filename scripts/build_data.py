"""Build the Copenhagen runtime datasets from local boundary and public sources."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union, transform as shapely_transform
from pyproj import Transformer
from shapely.geometry import LineString

try:
    from theme import LINE_COLORS
except ModuleNotFoundError:  # pragma: no cover - allows importing via the project root in tests
    from scripts.theme import LINE_COLORS


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PUBLIC_DIR = ROOT / "web" / "public" / "data"
TRANSIT_RULES_PATHS = [
    ROOT / "scripts" / "transit_rules.yaml",
]
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
    """Parse the canonical YAML config for service windows, transit rules, and allowed fare zones."""
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
    """Load the canonical YAML config for transit rules, service window, and allowed zones."""
    candidate = Path(path) if path is not None else TRANSIT_RULES_PATHS[0]
    if not candidate.exists():
        raise FileNotFoundError(f"Transit rules config is required: {candidate}")

    config = _parse_simple_yaml_config(candidate.read_text(encoding="utf-8"))
    rules: list[dict[str, str]] = []
    for entry in config["transit"]:
        rule = {str(k): str(v) for k, v in entry.items() if k in {"type", "pattern"} and v is not None}
        if rule:
            rules.append(rule)

    service = config.get("service", {})
    if service:
        service = {str(k): str(v).strip() for k, v in service.items() if str(v).strip()}

    return {
        "transit": rules,
        "service": service,
        "zones": [str(zone).strip() for zone in config.get("zones", []) if str(zone).strip()],
    }


def load_transit_rules(path: Path | None = None) -> list[dict[str, str]]:
    """Load transit selection rules from the canonical YAML config file."""
    return load_transit_config(path).get("transit", [])


DEFAULT_TRANSIT_CONFIG = load_transit_config()
DEFAULT_TRANSIT_SELECTION_RULES: list[dict[str, str]] = DEFAULT_TRANSIT_CONFIG["transit"]
DEFAULT_TRANSIT_SERVICE: dict[str, str] = DEFAULT_TRANSIT_CONFIG.get("service", {})
DEFAULT_TRANSIT_ZONES: set[str] = set(DEFAULT_TRANSIT_CONFIG.get("zones") or {"1", "2", "3", "4"})


def _parse_gtfs_time(value: str | None) -> int:
    """Parse a GTFS time string like 11:00:00 into minutes since midnight."""
    if value is None:
        return -1
    text = str(value).strip()
    if not text:
        return -1
    pieces = text.split(":")
    if len(pieces) < 2:
        return -1
    try:
        hours = int(pieces[0])
        minutes = int(pieces[1])
        seconds = int(pieces[2]) if len(pieces) > 2 else 0
        return hours * 60 * 60 + minutes * 60 + seconds
    except ValueError:
        return -1


def _service_window_active(stop_times: list[dict[str, str]], service_window: dict[str, str]) -> bool:
    """Return True when a trip has at least one stop inside the configured service window."""
    if not service_window:
        return True

    start_text = str(service_window.get("start_time") or "00:00").strip()
    end_text = str(service_window.get("end_time") or "23:59").strip()
    start_seconds = _parse_gtfs_time(start_text)
    end_seconds = _parse_gtfs_time(end_text)
    if start_seconds < 0 or end_seconds < 0:
        return True
    if end_seconds <= start_seconds:
        end_seconds += 24 * 60 * 60

    for row in stop_times:
        secs = _parse_gtfs_time(row.get("departure_time") or row.get("arrival_time"))
        if secs < 0:
            continue
        if secs >= start_seconds and secs <= end_seconds:
            return True
    return False


def normalize_route_pattern(pattern: str) -> str:
    """Convert a user-friendly route pattern into a full regex anchored to the whole name.

    Supports the shorthand tokens used by the map configuration, for example:
    "[digit]B" -> "^\\d+B$" and "[digit]S" -> "^\\d+S$".
    """
    clean = (pattern or "").strip()
    if not clean:
        return r".*"

    replacements = {
        "[digit]": r"\d+",
        "[digits]": r"\d+",
        "[letter]": r"[A-Za-z]",
        "[letters]": r"[A-Za-z]+",
    }
    regex = clean
    for token, replacement in replacements.items():
        regex = regex.replace(token, replacement)

    if not regex.startswith("^"):
        regex = f"^{regex}"
    if not regex.endswith("$"):
        regex = f"{regex}$"
    return regex


def matches_transit_rule(route_name: str | None, rule: dict[str, str], route_type: str | None = None) -> bool:
    """Return True when a GTFS route name matches a configured transit category/pattern rule."""
    name = str(route_name or "").strip()
    if not name:
        return False

    rule_type = (rule.get("type") or "").strip().lower()
    if rule_type in {"metro", "subway", "m"}:
        return bool(re.fullmatch(r"^M\d+$", name, flags=re.IGNORECASE))
    if rule_type in {"s-train", "s_train", "strain", "s-train-line"}:
        if route_type is not None and str(route_type).strip() != "109":
            return False
        return bool(re.fullmatch(r"^[A-Z]$", name, flags=re.IGNORECASE))
    if rule_type in {"bus", "buses"}:
        if name.upper() == "500S":
            return False
        pattern = rule.get("pattern")
        if not pattern:
            return False
        return bool(re.fullmatch(normalize_route_pattern(pattern), name, flags=re.IGNORECASE))
    return False


def select_gtfs_routes_for_rules(archive: zipfile.ZipFile, rules: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Return GTFS routes that match the provided transit category/pattern rules."""
    route_rows = load_csv_from_zip(archive, "routes.txt")
    return {
        row["route_id"]: row
        for row in route_rows
        if any(matches_transit_rule(row.get("route_short_name"), rule) for rule in rules)
    }


def _color_for_line(line: str) -> str:
    """Return a configured color for a line, falling back for valid GTFS variants."""
    if not line:
        return "#6a6a6a"
    return LINE_COLORS.get(line, "#6a6a6a")


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def download_if_missing(url: str, destination: Path) -> None:
    """Download a file only when it is not already present."""
    if destination.exists():
        return
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)


def load_region_boundary_feature() -> dict[str, Any]:
    """Read the committed Copenhagen playable-area boundary."""
    boundary_path = PUBLIC_DIR / "boundary.geojson"
    collection = json.loads(boundary_path.read_text())
    feature = (collection.get("features") or [None])[0]
    if not feature:
        raise RuntimeError(f"Boundary GeoJSON contains no feature: {boundary_path}")
    return feature


def load_movia_zone_shapes(boundary_shape: Any, allowed_names: set[str]) -> list[Any]:
    """Download Movia takstzone GeoJSON and return a list of zone shapes (WGS84) clipped to boundary.

    The ArcGIS service may return coordinates in different CRSs; we heuristically detect
    large coordinate values and transform from EPSG:25832 to EPSG:4326 when needed.
    """
    download_if_missing(MOVIA_ZONES_URL, MOVIA_ZONES_GEOJSON)
    source = json.loads(MOVIA_ZONES_GEOJSON.read_text())
    features = source.get("features", [])
    if not features:
        return []

    def _first_coord(feat: dict) -> tuple[float, float] | None:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords:
            return None
        # drill down to first numeric pair
        c = coords
        while isinstance(c, list) and c and isinstance(c[0], list):
            c = c[0]
        if isinstance(c, list) and len(c) >= 2 and isinstance(c[0], (int, float)):
            return c[0], c[1]
        return None

    first = _first_coord(features[0])
    need_transform = False
    if first:
        lon, lat = first
        if abs(lon) > 1000 or abs(lat) > 1000:
            need_transform = True

    transformer = None
    if need_transform:
        transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)

    zone_shapes: list[Any] = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        raw_name = str(props.get("Name") or props.get("NAME") or props.get("name") or "").strip()
        # Normalize zone name by extracting numeric tokens so values like '01', 'Zone 1',
        # or '1' all match the allowed_names set which contains plain digits.
        nums = re.findall(r"\d+", raw_name)
        name = nums[0].lstrip("0") if nums else raw_name
        if name not in allowed_names:
            continue
        geom = feat.get("geometry")
        if not geom:
            continue
        geom_shape = shape(geom)
        if need_transform and transformer is not None:
            geom_shape = shapely_transform(lambda x, y: transformer.transform(x, y), geom_shape)
        if not geom_shape.intersects(boundary_shape):
            continue
        clipped = geom_shape.intersection(boundary_shape)
        if clipped.is_empty:
            continue
        zone_shapes.append(clipped)

    return zone_shapes


def load_csv_from_zip(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    """Read a smaller CSV file from a GTFS ZIP archive."""
    with archive.open(name) as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))


def iter_csv_from_zip(archive: zipfile.ZipFile, name: str):
    """Yield CSV rows from a GTFS ZIP archive without materializing the full file."""
    with archive.open(name) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))


def _service_id_active_on_day(
    service_id: str | None,
    target_day: str | None,
    calendar_rows: list[dict[str, str]],
    calendar_dates: list[dict[str, str]],
) -> bool:
    """Return True when a GTFS service_id is active on the requested day."""
    if not service_id or not target_day:
        return True

    target_day = target_day.strip().lower()
    day_map = {
        "monday": "monday",
        "tuesday": "tuesday",
        "wednesday": "wednesday",
        "thursday": "thursday",
        "friday": "friday",
        "saturday": "saturday",
        "sunday": "sunday",
    }
    normalized = day_map.get(target_day, target_day)

    by_service: dict[str, dict[str, str]] = {row.get("service_id"): row for row in calendar_rows if row.get("service_id")}
    row = by_service.get(service_id)
    if row:
        if row.get(normalized, "0") == "1":
            return True

    for exception in calendar_dates:
        if exception.get("service_id") != service_id:
            continue
        # date-based service exceptions override the weekly schedule
        if exception.get("exception_type") == "1":
            return True
        if exception.get("exception_type") == "2":
            return False

    return False


def _filter_trips_by_service_window(
    archive: zipfile.ZipFile,
    trip_rows: list[dict[str, str]],
    service_window: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Only keep trips whose service exists on the configured day and whose stop times intersect the time range."""
    if not service_window:
        return trip_rows

    calendar_rows: list[dict[str, str]] = []
    calendar_dates: list[dict[str, str]] = []
    try:
        calendar_rows = load_csv_from_zip(archive, "calendar.txt")
    except KeyError:
        pass
    try:
        calendar_dates = load_csv_from_zip(archive, "calendar_dates.txt")
    except KeyError:
        pass
    if not calendar_rows and not calendar_dates:
        return trip_rows

    stop_times = load_csv_from_zip(archive, "stop_times.txt")
    stop_times_by_trip: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in stop_times:
        trip_id = row.get("trip_id")
        if not trip_id:
            continue
        stop_times_by_trip[trip_id].append(row)

    filtered: list[dict[str, str]] = []
    for trip in trip_rows:
        trip_id = trip.get("trip_id")
        if not trip_id:
            continue
        service_id = trip.get("service_id")
        if not _service_id_active_on_day(service_id, service_window.get("day"), calendar_rows, calendar_dates):
            continue
        if _service_window_active(stop_times_by_trip.get(trip_id, []), service_window):
            filtered.append(trip)
    return filtered


def load_selected_routes_and_trips(
    archive: zipfile.ZipFile,
    route_selector,
    service_window: dict[str, str] | None = None,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    route_rows = load_csv_from_zip(archive, "routes.txt")
    routes = {row["route_id"]: row for row in route_rows if route_selector(row)}
    trip_rows = [row for row in load_csv_from_zip(archive, "trips.txt") if row.get("route_id") in routes]
    if service_window:
        trip_rows = _filter_trips_by_service_window(archive, trip_rows, service_window)
    return routes, trip_rows


def load_selected_stop_rows(
    archive: zipfile.ZipFile,
    stop_ids_by_route: dict[str, set[str]],
    allowed_zones: set[str] | None = None,
    allowed_zone_shapes: list[Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Load stops referenced by the selected routes, optionally filtering by fare zones.

    The GTFS `stops.txt` may expose a zone identifier in a variety of column names. If
    `allowed_zones` is provided, we examine common zone-like columns and keep only stops
    that contain at least one numeric zone matching the allowed set.
    """
    selected_stop_ids = {stop_id for ids in stop_ids_by_route.values() for stop_id in ids}

    # If zone polygons are provided, build their union for point-in-polygon tests
    zone_union = None
    if allowed_zone_shapes:
        zone_union = unary_union(allowed_zone_shapes)

    def _row_in_allowed_zone(row: dict[str, str]) -> bool:
        # If no zone filter is active, keep the stop.
        if not allowed_zones and zone_union is None:
            return True

        has_zone_metadata = any(
            key in row and row.get(key) not in (None, "")
            for key in ("zone_id", "zone", "fare_zone", "fare_zone_id")
        )

        # When a zone filter is active, GTFS stops without zone metadata are not
        # eligible unless a polygon-based location test can prove they belong to the
        # allowed zone set. This keeps the selection aligned with the configured zones.
        if zone_union is not None:
            try:
                lon = float(row.get("stop_lon") or 0)
                lat = float(row.get("stop_lat") or 0)
            except Exception:
                return False
            if zone_union.contains(shape({"type": "Point", "coordinates": (lon, lat)})):
                return True
            return False

        if not has_zone_metadata:
            return False

        # Fallback: inspect textual fields for numeric zone tokens.
        for key in ("zone_id", "zone", "fare_zone", "fare_zone_id"):
            value = row.get(key)
            if not value:
                continue
            nums = re.findall(r"\d+", str(value))
            if any(num in allowed_zones for num in nums):
                return True
        return False

    return {
        row["stop_id"]: row
        for row in load_csv_from_zip(archive, "stops.txt")
        if row.get("stop_id") in selected_stop_ids and _row_in_allowed_zone(row)
    }


def clean_station_name(name: str) -> str:
    return re.sub(r"\s*\(Metro\)\s*", "", str(name or "")).strip()


def normalize_station_name(name: str) -> str:
    normalized = str(name or "").casefold().replace("ø", "o").replace("å", "a").replace("æ", "ae")
    normalized = re.sub(r"\(.*?\)", "", normalized)
    normalized = re.sub(r"\bst\.?\b", "", normalized)
    normalized = normalized.replace("station", "")
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


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


def _add_station_feature(
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    stop: dict[str, str],
    line: str,
    network: str,
) -> None:
    name = clean_station_name(stop.get("stop_name", stop["stop_id"]))
    if not name:
        return
    lat = float(stop["stop_lat"])
    lon = float(stop["stop_lon"])
    key = (normalize_station_name(name), round(lat, 6), round(lon, 6))
    station = station_index.setdefault(
        key,
        {
            "type": "Feature",
            "properties": {
                "name": name,
                "lines": [],
                "networks": [],
                "stop_id": stop["stop_id"],
                "source": "Rejseplanen GTFS",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
        },
    )
    if line not in station["properties"]["lines"]:
        station["properties"]["lines"].append(line)
    if network not in station["properties"]["networks"]:
        station["properties"]["networks"].append(network)


def _dedupe_coords(coords: list[list[float]]) -> list[list[float]]:
    """Remove consecutive duplicate coordinate pairs."""
    if not coords:
        return coords
    out: list[list[float]] = [coords[0]]
    for pt in coords[1:]:
        if pt[0] != out[-1][0] or pt[1] != out[-1][1]:
            out.append(pt)
    return out


def merge_route_segments(segments: list[list[list[float]]], gap_tolerance: float = 0.002) -> list[list[float]]:
    """Join nearby route fragments into a single line when the GTFS shapes are split by gaps."""
    if not segments:
        return []

    remaining = [segment[:] for segment in segments if len(segment) >= 2]
    if not remaining:
        return []

    merged = remaining.pop(0)
    while remaining:
        best_index = None
        best_mode = None
        best_candidate = None
        best_distance = float("inf")

        for candidate_index, candidate in enumerate(remaining):
            for mode, anchor_point, candidate_point in (
                ("append_same", merged[-1], candidate[0]),
                ("append_reverse", merged[-1], candidate[-1]),
                ("prepend_same", merged[0], candidate[0]),
                ("prepend_reverse", merged[0], candidate[-1]),
            ):
                distance = math.hypot(candidate_point[0] - anchor_point[0], candidate_point[1] - anchor_point[1])
                if distance <= gap_tolerance and distance < best_distance:
                    best_distance = distance
                    best_index = candidate_index
                    best_mode = mode
                    best_candidate = candidate

        if best_index is None or best_mode is None or best_candidate is None:
            break

        candidate = remaining.pop(best_index)
        if best_mode == "append_same":
            merged = merged + candidate[1:]
        elif best_mode == "append_reverse":
            merged = merged + candidate[::-1][1:]
        elif best_mode == "prepend_same":
            merged = candidate + merged[1:]
        elif best_mode == "prepend_reverse":
            merged = candidate[::-1] + merged[1:]

    return _dedupe_coords(merged)


def _route_shape_quality(coords: list[list[float]]) -> float:
    """Prefer the least backtracking, most coherent path when multiple route shapes exist."""
    if len(coords) < 2:
        return -float("inf")

    total_length = 0.0
    reversal_penalty = 0.0
    repeated_points = 0
    seen: set[tuple[float, float]] = set()

    for index, point in enumerate(coords):
        key = (round(point[0], 6), round(point[1], 6))
        if key in seen:
            repeated_points += 1
        seen.add(key)

        if index == 0:
            continue
        prev = coords[index - 1]
        total_length += math.hypot(point[0] - prev[0], point[1] - prev[1])
        if index >= 2:
            before = coords[index - 2]
            prev_vec = (prev[0] - before[0], prev[1] - before[1])
            curr_vec = (point[0] - prev[0], point[1] - prev[1])
            prev_norm = math.hypot(*prev_vec)
            curr_norm = math.hypot(*curr_vec)
            if prev_norm > 0 and curr_norm > 0:
                dot = (prev_vec[0] * curr_vec[0] + prev_vec[1] * curr_vec[1]) / (prev_norm * curr_norm)
                if dot < 0:
                    reversal_penalty += 1.0

    return total_length - (repeated_points * 5000.0) - (reversal_penalty * 2500.0)


def select_best_route_shape(candidates: list[list[list[float]]]) -> list[list[float]]:
    """Choose the least backtracking, most coherent shape among overlapping GTFS variants."""
    cleaned = [coords for coords in candidates if len(coords) >= 2]
    if not cleaned:
        return []
    return max(cleaned, key=_route_shape_quality)


def trim_route_to_zone_stops(
    coords: list[list[float]],
    ordered_stops: list[str],
    stop_rows: dict[str, dict[str, str]],
    stop_rows_all: dict[str, dict[str, str]],
) -> list[list[float]]:
    """Stop the line at the first and last station that are still inside the selected zone."""
    if len(coords) < 2 or not ordered_stops:
        return coords

    in_zone = [stop_id for stop_id in ordered_stops if stop_id in stop_rows]
    if len(in_zone) < 2:
        return coords

    first_stop_id = in_zone[0]
    last_stop_id = in_zone[-1]
    first_stop = stop_rows_all.get(first_stop_id)
    last_stop = stop_rows_all.get(last_stop_id)
    if not first_stop or not last_stop:
        return coords

    first_point = [float(first_stop["stop_lon"]), float(first_stop["stop_lat"])]
    last_point = [float(last_stop["stop_lon"]), float(last_stop["stop_lat"])]

    def nearest_index(point: list[float]) -> int:
        best_index = 0
        best_distance = float("inf")
        for idx, coord in enumerate(coords):
            distance = math.hypot(coord[0] - point[0], coord[1] - point[1])
            if distance < best_distance:
                best_distance = distance
                best_index = idx
        return best_index

    start_idx = nearest_index(first_point)
    end_idx = nearest_index(last_point)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    trimmed = coords[start_idx : end_idx + 1]
    return _dedupe_coords(trimmed) if len(trimmed) >= 2 else coords


def clip_route_to_zone_shapes(coords: list[list[float]], allowed_zone_shapes: list[Any] | None) -> list[list[float]]:
    """Clip route geometry to the selected zone polygons and keep only the valid zone segment."""
    if not allowed_zone_shapes or len(coords) < 2:
        return coords

    try:
        zone_union = unary_union(allowed_zone_shapes)
        clipped = LineString(coords).intersection(zone_union)
        if clipped.is_empty:
            return []

        segments: list[Any] = []
        if clipped.geom_type == "LineString":
            segments = [clipped]
        elif clipped.geom_type == "MultiLineString":
            segments = list(clipped.geoms)
        elif clipped.geom_type == "GeometryCollection":
            segments = [geom for geom in clipped.geoms if geom.geom_type in {"LineString", "MultiLineString"}]
            if segments and segments[0].geom_type == "MultiLineString":
                segments = list(segments[0].geoms)

        if not segments:
            return []

        best = max(segments, key=lambda geom: geom.length)
        if best.geom_type == "MultiLineString":
            best = max(best.geoms, key=lambda geom: geom.length)
        if best.is_empty:
            return []
        return [list(point) for point in mapping(best)["coordinates"]]
    except Exception:
        return coords


def build_transit_features_for_rules(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    rules: list[dict[str, str]],
    network_name: str,
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Generic GTFS route builder shared by metro, S-train, and bus selections."""
    route_selector = lambda row: any(
        matches_transit_rule(row.get("route_short_name"), rule, row.get("route_type"))
        for rule in rules
    )
    routes, trip_rows = load_selected_routes_and_trips(archive, route_selector, service_window=DEFAULT_TRANSIT_SERVICE)
    if not routes:
        return []

    shape_ids_by_route: dict[str, set[str]] = defaultdict(set)
    for trip in trip_rows:
        shape_id = trip.get("shape_id")
        if shape_id:
            shape_ids_by_route[trip["route_id"]].add(shape_id)

    selected_shape_ids = {shape_id for ids in shape_ids_by_route.values() for shape_id in ids}
    shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for row in iter_csv_from_zip(archive, "shapes.txt"):
        shape_id = row.get("shape_id")
        if shape_id not in selected_shape_ids:
            continue
        shape_points[shape_id].append(
            (
                int(row.get("shape_pt_sequence") or 0),
                float(row["shape_pt_lon"]),
                float(row["shape_pt_lat"]),
            )
        )

    stop_ids_by_route: dict[str, set[str]] = defaultdict(set)
    trip_route = {trip["trip_id"]: trip["route_id"] for trip in trip_rows}
    stop_times_by_trip: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in iter_csv_from_zip(archive, "stop_times.txt"):
        trip_id = row.get("trip_id")
        if trip_id in trip_route:
            stop_times_by_trip[trip_id].append((int(row.get("stop_sequence") or 0), row["stop_id"]))

    ordered_stops_by_route: dict[str, list[str]] = {}
    for trip in trip_rows:
        route_id = trip["route_id"]
        trip_id = trip["trip_id"]
        entries = stop_times_by_trip.get(trip_id)
        if not entries:
            continue
        ordered = [stop_id for _, stop_id in sorted(entries)]
        if len(ordered) < 2:
            continue
        ordered_stops_by_route.setdefault(route_id, []).append(ordered)

    route_stop_ids_by_route: dict[str, set[str]] = {
        route_id: {stop_id for ordered in sequences for stop_id in ordered}
        for route_id, sequences in ordered_stops_by_route.items()
    }
    stop_rows_all = load_selected_stop_rows(archive, route_stop_ids_by_route, allowed_zone_shapes=None, allowed_zones=None)
    stop_rows = load_selected_stop_rows(
        archive,
        route_stop_ids_by_route,
        allowed_zone_shapes=allowed_zone_shapes,
        allowed_zones=set(DEFAULT_TRANSIT_ZONES),
    )

    trip_stop_paths: dict[str, list[list[float]]] = defaultdict(list)
    for route_id, sequences in ordered_stops_by_route.items():
        for ordered in sequences:
            filtered = [stop_id for stop_id in ordered if stop_id in stop_rows]
            if len(filtered) < 2:
                continue
            stop_path = [[float(stop_rows_all[stop_id]["stop_lon"]), float(stop_rows_all[stop_id]["stop_lat"])] for stop_id in filtered]
            if len(stop_path) >= 2:
                trip_stop_paths[route_id].append(_dedupe_coords(stop_path))

    for route_id, sequences in ordered_stops_by_route.items():
        route_candidates = [
            [stop_id for stop_id in ordered if stop_id in stop_rows]
            for ordered in sequences
            if len([stop_id for stop_id in ordered if stop_id in stop_rows]) >= 2
        ]
        if route_candidates:
            best = max(route_candidates, key=len)
            stop_ids_by_route[route_id] = set(best)
            ordered_stops_by_route[route_id] = best
        else:
            stop_ids_by_route[route_id] = set()
            ordered_stops_by_route[route_id] = []

    line_features_by_line: dict[str, dict[str, Any]] = {}
    for route_id, route in sorted(routes.items(), key=lambda item: item[1].get("route_short_name", "")):
        line = route.get("route_short_name")
        if not line:
            continue

        route_stop_ids = stop_ids_by_route.get(route_id, set())
        if not any(stop_id in stop_rows for stop_id in route_stop_ids):
            continue

        ordered = ordered_stops_by_route.get(route_id)
        raw_segments: list[list[list[float]]] = []
        if trip_stop_paths.get(route_id):
            raw_segments.extend(trip_stop_paths[route_id])
        if not raw_segments:
            for shape_id in sorted(shape_ids_by_route.get(route_id, [])):
                points = sorted(shape_points.get(shape_id, []))
                if len(points) < 2:
                    continue
                shape_coords = [[lon, lat] for _, lon, lat in points]
                if len(shape_coords) >= 2:
                    raw_segments.append(shape_coords)

        if not raw_segments and ordered:
            filtered_indices = [i for i, stop_id in enumerate(ordered) if stop_id in stop_rows]
            if filtered_indices:
                start_idx, end_idx = filtered_indices[0], filtered_indices[-1]
                fallback_coords: list[list[float]] = []
                for stop_id in ordered[start_idx : end_idx + 1]:
                    stop = stop_rows_all.get(stop_id)
                    if stop:
                        fallback_coords.append([float(stop["stop_lon"]), float(stop["stop_lat"])])
                if len(fallback_coords) >= 2:
                    raw_segments.append(fallback_coords)

        merged_shape = merge_route_segments(raw_segments)
        candidate_coords = select_best_route_shape([merged_shape] if merged_shape else raw_segments)
        if trip_stop_paths.get(route_id):
            stop_sequence = max(trip_stop_paths[route_id], key=len)
            if stop_sequence and len(stop_sequence) >= 2:
                candidate_coords = stop_sequence
        if ordered and stop_rows:
            candidate_coords = trim_route_to_zone_stops(candidate_coords, ordered, stop_rows, stop_rows_all)
        coords = clip_route_to_zone_shapes(candidate_coords, allowed_zone_shapes)
        if not coords and candidate_coords and allowed_zone_shapes:
            coords = candidate_coords
        coords = _dedupe_coords(coords)
        if len(coords) < 2:
            continue

        route_label = ""
        if ordered:
            filtered_indices = [i for i, stop_id in enumerate(ordered) if stop_id in stop_rows]
            if filtered_indices:
                start_idx, end_idx = filtered_indices[0], filtered_indices[-1]
                first_stop = stop_rows_all.get(ordered[start_idx])
                last_stop = stop_rows_all.get(ordered[end_idx])
                if first_stop and last_stop:
                    route_label = f"{clean_station_name(first_stop.get('stop_name', ''))} – {clean_station_name(last_stop.get('stop_name', ''))}"

        feature = {
            "type": "Feature",
            "properties": {
                "network": network_name,
                "line": line,
                "route_id": route_id,
                "route": route_label,
                "color": _color_for_line(line) if line else "#6a6a6a",
                "source": "Rejseplanen GTFS",
                "service_state": route.get("service_state", ""),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        current = line_features_by_line.get(line)
        if current is None or len(coords) > len(current["geometry"]["coordinates"]):
            line_features_by_line[line] = feature

    line_features = list(line_features_by_line.values())

    for route_id, stop_ids in stop_ids_by_route.items():
        line = routes[route_id].get("route_short_name")
        for stop_id in stop_ids:
            stop = stop_rows.get(stop_id)
            if not stop or not stop.get("stop_lat") or not stop.get("stop_lon"):
                continue
            _add_station_feature(station_index, stop, line, network_name)

    return line_features


def build_metro_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return build_transit_features_for_rules(
        archive,
        station_index,
        [{"type": "metro"}],
        network_name="metro",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_stog_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return build_transit_features_for_rules(
        archive,
        station_index,
        [{"type": "s-train"}],
        network_name="s-tog",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_bus_transport_features(
    archive: zipfile.ZipFile,
    station_index: dict[tuple[str, float, float], dict[str, Any]],
    allowed_zone_shapes: list[Any] | None = None,
    route_name_patterns: list[str] | None = None,
    transit_rules: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build all bus routes matching the configured GTFS patterns, without hardcoded route lists."""
    if transit_rules is None:
        transit_rules = [rule for rule in DEFAULT_TRANSIT_SELECTION_RULES if rule.get("type") == "bus"]

    return build_transit_features_for_rules(
        archive,
        station_index,
        transit_rules,
        network_name="bus",
        allowed_zone_shapes=allowed_zone_shapes,
    )


def build_transport_datasets(allowed_zone_shapes: list[Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    download_if_missing(GTFS_URL, GTFS_ZIP)
    station_index: dict[tuple[str, float, float], dict[str, Any]] = {}
    with zipfile.ZipFile(GTFS_ZIP) as archive:
        line_features = build_metro_transport_features(archive, station_index, allowed_zone_shapes=allowed_zone_shapes)
        line_features.extend(build_stog_transport_features(archive, station_index, allowed_zone_shapes=allowed_zone_shapes))
        line_features.extend(
            build_bus_transport_features(
                archive,
                station_index,
                allowed_zone_shapes=allowed_zone_shapes,
                transit_rules=[rule for rule in DEFAULT_TRANSIT_SELECTION_RULES if rule.get("type") == "bus"],
            )
        )

    station_features = list(station_index.values())
    for station in station_features:
        station["properties"]["lines"].sort()
        station["properties"]["networks"].sort()
    line_features.sort(key=lambda feat: (feat["properties"]["network"], feat["properties"]["line"], feat["properties"].get("shape_id", "")))
    station_features.sort(key=lambda feat: feat["properties"]["name"])
    print(
        "Transit import summary: "
        f"routes={len(line_features)} stations={len(station_features)} "
        f"networks={ {feat['properties']['network'] for feat in line_features} }"
    )
    return (
        {"type": "FeatureCollection", "features": line_features},
        {"type": "FeatureCollection", "features": station_features},
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def main() -> None:
    """Build all derived data files for the Copenhagen playable area."""
    ensure_dirs()
    boundary_feature = load_region_boundary_feature()
    # Load Movia takstzone polygons for zones 1-4 and pass them to the transport builder.
    boundary_shape = shape(boundary_feature["geometry"])
    # Attempt to download Movia zones and select zones 1-4 clipped to the boundary.
    try:
        movia_zones = load_movia_zone_shapes(boundary_shape, {"1", "2", "3", "4"})
    except Exception:
        movia_zones = None

    transport_lines, transport_stations = build_transport_datasets(allowed_zone_shapes=movia_zones)
    municipalities = build_municipalities_dataset(boundary_feature)
    postnumre = build_postnumre_dataset(boundary_feature)
    opstillingskredse = build_opstillingskredse_dataset(boundary_feature)
    sogne = build_sogne_dataset(boundary_feature)
    boundary = {
        "type": "FeatureCollection",
        "features": [boundary_feature],
    }

    write_json(PUBLIC_DIR / "municipalities.geojson", municipalities)
    write_json(PUBLIC_DIR / "postnumre.geojson", postnumre)
    write_json(PUBLIC_DIR / "opstillingskredse.geojson", opstillingskredse)
    write_json(PUBLIC_DIR / "sogne.geojson", sogne)
    write_json(PUBLIC_DIR / "boundary.geojson", boundary)
    write_json(PUBLIC_DIR / "transport-lines.geojson", transport_lines)
    write_json(PUBLIC_DIR / "transport-stations.geojson", transport_stations)


if __name__ == "__main__":
    main()
