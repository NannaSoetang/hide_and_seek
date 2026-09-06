"""GTFS parsing and transit-selection helpers for the data pipeline."""

from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from datetime import date
from typing import Any

from shapely.geometry import shape
from shapely.ops import unary_union

from scripts.config.data_config import DEFAULT_TRANSIT_SERVICE
from scripts.io.data_io import load_csv_from_zip


def parse_gtfs_time(value: str | None) -> int:
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


def normalize_route_pattern(pattern: str) -> str:
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
        return bool(pattern and re.fullmatch(normalize_route_pattern(pattern), name, flags=re.IGNORECASE))
    return False


def service_window_active(stop_times: list[dict[str, str]], service_window: dict[str, str]) -> bool:
    if not service_window:
        return True

    start_seconds = parse_gtfs_time(str(service_window.get("start_time") or "00:00").strip())
    end_seconds = parse_gtfs_time(str(service_window.get("end_time") or "23:59").strip())
    if start_seconds < 0 or end_seconds < 0:
        return True
    if end_seconds <= start_seconds:
        end_seconds += 24 * 60 * 60

    return any(
        start_seconds <= seconds <= end_seconds
        for row in stop_times
        if (seconds := parse_gtfs_time(row.get("departure_time") or row.get("arrival_time"))) >= 0
    )


def service_id_active_on_day(
    service_id: str | None,
    service_window: dict[str, str],
    calendar_rows: list[dict[str, str]],
    calendar_dates: list[dict[str, str]],
) -> bool:
    if not service_id:
        return True

    configured_date = service_window.get("date")
    target_date = date.fromisoformat(configured_date) if configured_date else None
    target_day = target_date.strftime("%A").lower() if target_date else service_window.get("day", "").strip().lower()
    if not target_day:
        return True

    by_service = {row.get("service_id"): row for row in calendar_rows if row.get("service_id")}
    row = by_service.get(service_id)
    active = bool(row and row.get(target_day, "0") == "1")
    if target_date and row:
        gtfs_date = target_date.strftime("%Y%m%d")
        active = active and row.get("start_date", "") <= gtfs_date <= row.get("end_date", "")

    if not target_date:
        return active

    for exception in calendar_dates:
        if exception.get("service_id") != service_id or exception.get("date") != target_date.strftime("%Y%m%d"):
            continue
        if exception.get("exception_type") == "1":
            return True
        if exception.get("exception_type") == "2":
            return False
    return active


def filter_trips_by_service_window(
    archive: zipfile.ZipFile,
    trip_rows: list[dict[str, str]],
    service_window: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if not service_window:
        return trip_rows

    try:
        calendar_rows = load_csv_from_zip(archive, "calendar.txt")
    except KeyError:
        calendar_rows = []
    try:
        calendar_dates = load_csv_from_zip(archive, "calendar_dates.txt")
    except KeyError:
        calendar_dates = []
    if not calendar_rows and not calendar_dates:
        return trip_rows

    stop_times_by_trip: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv_from_zip(archive, "stop_times.txt"):
        if row.get("trip_id"):
            stop_times_by_trip[row["trip_id"]].append(row)

    filtered = []
    for trip in trip_rows:
        trip_id = trip.get("trip_id")
        if not trip_id:
            continue
        if not service_id_active_on_day(trip.get("service_id"), service_window, calendar_rows, calendar_dates):
            continue
        if service_window_active(stop_times_by_trip.get(trip_id, []), service_window):
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
        trip_rows = filter_trips_by_service_window(archive, trip_rows, service_window)
    return routes, trip_rows


def load_selected_stop_rows(
    archive: zipfile.ZipFile,
    stop_ids_by_route: dict[str, set[str]],
    allowed_zones: set[str] | None = None,
    allowed_zone_shapes: list[Any] | None = None,
) -> dict[str, dict[str, str]]:
    selected_stop_ids = {stop_id for ids in stop_ids_by_route.values() for stop_id in ids}
    zone_union = unary_union(allowed_zone_shapes) if allowed_zone_shapes else None

    def row_in_allowed_zone(row: dict[str, str]) -> bool:
        if not allowed_zones and zone_union is None:
            return True
        has_zone_metadata = any(
            key in row and row.get(key) not in (None, "")
            for key in ("zone_id", "zone", "fare_zone", "fare_zone_id")
        )
        if zone_union is not None:
            try:
                point = shape({
                    "type": "Point",
                    "coordinates": (float(row.get("stop_lon") or 0), float(row.get("stop_lat") or 0)),
                })
            except (TypeError, ValueError):
                return False
            return zone_union.contains(point)
        if not has_zone_metadata:
            return False
        for key in ("zone_id", "zone", "fare_zone", "fare_zone_id"):
            value = row.get(key)
            if value and any(number in allowed_zones for number in re.findall(r"\d+", str(value))):
                return True
        return False

    return {
        row["stop_id"]: row
        for row in load_csv_from_zip(archive, "stops.txt")
        if row.get("stop_id") in selected_stop_ids and row_in_allowed_zone(row)
    }
