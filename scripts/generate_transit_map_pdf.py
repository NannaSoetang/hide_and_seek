#!/usr/bin/env python3
"""Generate a vector PDF transit map from the built GeoJSON datasets."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from pyproj import Transformer
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from theme import ADMIN_LAYERS, LINE_COLORS, lines_for_network


TRANSPORT_LINE_ORDER = {
    network: [line["line"] for line in lines_for_network(network)]
    for network in ("metro", "s-tog")
}

ADMIN_LAYER_SPECS = [
    {
        "id": Path(layer["dataFile"]).stem,
        "path": Path("web/public/data") / layer["dataFile"],
        "color": layer["color"],
        "width": layer["pdfWidth"],
    }
    for layer in ADMIN_LAYERS
]

DEFAULT_INPUT_LINES = Path("web/public/data/transport-lines.geojson")
DEFAULT_INPUT_STATIONS = Path("web/public/data/transport-stations.geojson")
DEFAULT_INPUT_BOUNDARY = Path("web/public/data/boundary.geojson")
DEFAULT_OUTPUT = Path("transit-map.pdf")

WEB_MERCATOR = "EPSG:3857"
WGS84 = "EPSG:4326"
TILE_SIZE = 256
ORIGIN_SHIFT = 20037508.342789244
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


@dataclass(frozen=True)
class PdfMapConfig:
    """Rendering knobs that can be tuned from the CLI."""

    orientation: str = "auto"
    margin: float = 16.0
    line_width: float = 2.45
    line_casing_width: float = 5.2
    station_radius: float = 3.3
    station_stroke_width: float = 1.1
    network_padding: float = 0.04
    background_zoom: int = 15
    tile_url: str = "https://basemaps.cartocdn.com/rastertiles/light_nolabels/{z}/{x}/{y}.png"
    tile_cache_dir: Path = Path(".cache/transit-map/tiles")
    boundary_color: str = "#ff4d00"
    boundary_width: float = 2.0
    boundary_casing_width: float = 4.4
    label_clearance: float = 4.5
    label_font_size: float = 7.8
    label_padding_x: float = 2.5
    label_padding_y: float = 1.8
    label_gap: float = 2.0


@dataclass(frozen=True)
class ProjectedPoint:
    x: float
    y: float


@dataclass(frozen=True)
class LineRecord:
    network: str
    line_id: str
    color: str
    coordinates: list[ProjectedPoint]


@dataclass(frozen=True)
class StationRecord:
    name: str
    display_name: str
    lines: tuple[str, ...]
    networks: tuple[str, ...]
    point: ProjectedPoint


@dataclass(frozen=True)
class MapBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def padded(self, fraction: float) -> "MapBounds":
        pad_x = self.width * fraction
        pad_y = self.height * fraction
        return MapBounds(
            self.min_x - pad_x,
            self.min_y - pad_y,
            self.max_x + pad_x,
            self.max_y + pad_y,
        )


@dataclass(frozen=True)
class PageTransform:
    page_width: float
    page_height: float
    bounds: MapBounds
    scale: float
    offset_x: float
    offset_y: float

    def map_point(self, point: ProjectedPoint) -> tuple[float, float]:
        x = self.offset_x + (point.x - self.bounds.min_x) * self.scale
        y = self.offset_y + (point.y - self.bounds.min_y) * self.scale
        return x, y

    def map_distance(self, distance: float) -> float:
        return distance * self.scale


def load_geojson(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    return json.loads(path.read_text())


def choose_font() -> str:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    for font_path in candidates:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("TransitMapSans", str(font_path)))
            return "TransitMapSans"
    return "Helvetica"


def project_coordinates(coordinates: Iterable[tuple[float, float]], transformer: Transformer) -> list[ProjectedPoint]:
    return [ProjectedPoint(*transformer.transform(lon, lat)) for lon, lat in coordinates]


def mercator_pixel_to_point(pixel_x: float, pixel_y: float, zoom: int) -> ProjectedPoint:
    map_size = TILE_SIZE * (2**zoom)
    mx = pixel_x / map_size * (2 * ORIGIN_SHIFT) - ORIGIN_SHIFT
    my = ORIGIN_SHIFT - pixel_y / map_size * (2 * ORIGIN_SHIFT)
    return ProjectedPoint(mx, my)


def point_to_mercator_pixel(point: ProjectedPoint, zoom: int) -> tuple[float, float]:
    map_size = TILE_SIZE * (2**zoom)
    pixel_x = (point.x + ORIGIN_SHIFT) / (2 * ORIGIN_SHIFT) * map_size
    pixel_y = (ORIGIN_SHIFT - point.y) / (2 * ORIGIN_SHIFT) * map_size
    return pixel_x, pixel_y


def points_bounds(points: Iterable[ProjectedPoint]) -> MapBounds:
    iterator = iter(points)
    first = next(iterator)
    min_x = max_x = first.x
    min_y = max_y = first.y
    for point in iterator:
        min_x = min(min_x, point.x)
        min_y = min(min_y, point.y)
        max_x = max(max_x, point.x)
        max_y = max(max_y, point.y)
    return MapBounds(min_x, min_y, max_x, max_y)


def merge_bounds(existing: MapBounds | None, points: Iterable[ProjectedPoint]) -> MapBounds:
    point_list = list(points)
    if not point_list:
        raise ValueError("Cannot compute map bounds from an empty point set")
    bounds = points_bounds(point_list)
    if existing is None:
        return bounds
    return MapBounds(
        min(existing.min_x, bounds.min_x),
        min(existing.min_y, bounds.min_y),
        max(existing.max_x, bounds.max_x),
        max(existing.max_y, bounds.max_y),
    )


def normalize_station_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").replace("(Metro)", "")).strip().lower()


def display_station_name(name: str) -> str:
    cleaned = str(name or "").replace("(Metro)", "")
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_boundary_rings(boundary_geojson: dict) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    for feature in boundary_geojson.get("features", []):
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            rings.extend(coordinates)
        elif geometry_type == "MultiPolygon":
            for polygon in coordinates:
                rings.extend(polygon)
    return [ring for ring in rings if len(ring) >= 2]


def build_render_data(
    lines_geojson: dict,
    stations_geojson: dict,
) -> tuple[list[LineRecord], list[StationRecord], MapBounds]:
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    line_records: list[LineRecord] = []
    station_records: list[StationRecord] = []
    bounds: MapBounds | None = None

    for feature in lines_geojson.get("features", []):
        properties = feature.get("properties") or {}
        network = str(properties.get("network") or "")
        line_id = str(properties.get("line") or "")
        coordinates = feature.get("geometry", {}).get("coordinates") or []
        if not network or not line_id or len(coordinates) < 2:
            continue
        projected = project_coordinates(coordinates, transformer)
        line_records.append(
            LineRecord(
                network=network,
                line_id=line_id,
                color=str(properties.get("color") or LINE_COLORS[line_id]),
                coordinates=projected,
            )
        )
        bounds = merge_bounds(bounds, projected)

    for feature in stations_geojson.get("features", []):
        properties = feature.get("properties") or {}
        name = str(properties.get("name") or "").strip()
        networks = tuple(str(value) for value in properties.get("networks") or [])
        lines = tuple(str(value) for value in properties.get("lines") or [])
        coordinates = feature.get("geometry", {}).get("coordinates") or []
        if len(coordinates) != 2:
            continue
        projected_point = ProjectedPoint(*transformer.transform(coordinates[0], coordinates[1]))
        station_records.append(
            StationRecord(
                name=normalize_station_name(name),
                display_name=display_station_name(name),
                lines=lines,
                networks=networks,
                point=projected_point,
            )
        )
        bounds = merge_bounds(bounds, [projected_point])

    if bounds is None:
        raise ValueError("No geometry found in the transport datasets")

    return line_records, station_records, bounds


def line_groups(line_records: list[LineRecord]) -> dict[tuple[str, str], list[LineRecord]]:
    groups: dict[tuple[str, str], list[LineRecord]] = {}
    for record in line_records:
        groups.setdefault((record.network, record.line_id), []).append(record)
    return groups


def longest_record(records: list[LineRecord]) -> LineRecord:
    return max(records, key=lambda record: polyline_length(record.coordinates))


def polyline_length(coordinates: list[ProjectedPoint]) -> float:
    return sum(
        math.hypot(right.x - left.x, right.y - left.y)
        for left, right in zip(coordinates, coordinates[1:])
    )


def point_along_polyline(coordinates: list[ProjectedPoint], fraction: float = 0.5) -> tuple[ProjectedPoint, tuple[float, float]]:
    if len(coordinates) < 2:
        point = coordinates[0]
        return point, (1.0, 0.0)

    total = polyline_length(coordinates)
    target = total * fraction
    travelled = 0.0
    for left, right in zip(coordinates, coordinates[1:]):
        segment = math.hypot(right.x - left.x, right.y - left.y)
        if travelled + segment >= target:
            if segment == 0:
                return left, (1.0, 0.0)
            local = (target - travelled) / segment
            point = ProjectedPoint(
                left.x + (right.x - left.x) * local,
                left.y + (right.y - left.y) * local,
            )
            tangent = (right.x - left.x, right.y - left.y)
            return point, tangent
        travelled += segment

    left = coordinates[-2]
    right = coordinates[-1]
    return right, (right.x - left.x, right.y - left.y)


def orient_page(bounds: MapBounds, config: PdfMapConfig) -> tuple[tuple[float, float], MapBounds, float, float, float]:
    page_sizes = [portrait(A4), landscape(A4)]
    if config.orientation == "portrait":
        page_sizes = [portrait(A4)]
    elif config.orientation == "landscape":
        page_sizes = [landscape(A4)]

    best_choice: tuple[tuple[float, float], MapBounds, float, float, float] | None = None
    for page_width, page_height in page_sizes:
        padded_bounds = bounds.padded(config.network_padding)
        available_width = page_width - 2 * config.margin
        available_height = page_height - 2 * config.margin
        scale = min(available_width / padded_bounds.width, available_height / padded_bounds.height)
        used_width = padded_bounds.width * scale
        used_height = padded_bounds.height * scale
        offset_x = config.margin + (available_width - used_width) / 2.0
        offset_y = config.margin + (available_height - used_height) / 2.0
        choice = ((page_width, page_height), padded_bounds, scale, offset_x, offset_y)
        if best_choice is None or scale > best_choice[2]:
            best_choice = choice

    assert best_choice is not None
    return best_choice


def make_transform(page_width: float, page_height: float, bounds: MapBounds, scale: float, offset_x: float, offset_y: float) -> PageTransform:
    return PageTransform(
        page_width=page_width,
        page_height=page_height,
        bounds=bounds,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
    )


def draw_tile_background(
    canvas: Canvas,
    transform: PageTransform,
    config: PdfMapConfig,
) -> None:
    zoom = config.background_zoom
    min_pixel_x, max_pixel_y = point_to_mercator_pixel(
        ProjectedPoint(transform.bounds.min_x, transform.bounds.min_y),
        zoom,
    )
    max_pixel_x, min_pixel_y = point_to_mercator_pixel(
        ProjectedPoint(transform.bounds.max_x, transform.bounds.max_y),
        zoom,
    )

    tile_x0 = int(math.floor(min(min_pixel_x, max_pixel_x) / TILE_SIZE))
    tile_x1 = int(math.floor(max(min_pixel_x, max_pixel_x) / TILE_SIZE))
    tile_y0 = int(math.floor(min(min_pixel_y, max_pixel_y) / TILE_SIZE))
    tile_y1 = int(math.floor(max(min_pixel_y, max_pixel_y) / TILE_SIZE))

    session = requests.Session()
    session.headers.update({"User-Agent": "hide_and_seek-transit-map/1.0"})

    for tile_x in range(tile_x0, tile_x1 + 1):
        for tile_y in range(tile_y0, tile_y1 + 1):
            tile_path = config.tile_cache_dir / str(zoom) / str(tile_x) / f"{tile_y}.png"
            if tile_path.exists():
                tile_bytes = tile_path.read_bytes()
            else:
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                response = session.get(config.tile_url.format(z=zoom, x=tile_x, y=tile_y), timeout=30)
                response.raise_for_status()
                tile_bytes = response.content
                tile_path.write_bytes(tile_bytes)

            tile_top_left = mercator_pixel_to_point(tile_x * TILE_SIZE, tile_y * TILE_SIZE, zoom)
            tile_bottom_right = mercator_pixel_to_point((tile_x + 1) * TILE_SIZE, (tile_y + 1) * TILE_SIZE, zoom)
            x0, y0 = transform.map_point(ProjectedPoint(tile_top_left.x, tile_bottom_right.y))
            x1, y1 = transform.map_point(ProjectedPoint(tile_bottom_right.x, tile_top_left.y))
            canvas.drawImage(
                ImageReader(BytesIO(tile_bytes)),
                x0,
                y0,
                width=x1 - x0,
                height=y1 - y0,
                preserveAspectRatio=False,
                mask="auto",
            )


def draw_boundary(canvas: Canvas, transform: PageTransform, boundary_rings: list[list[ProjectedPoint]], config: PdfMapConfig) -> None:
    for ring in boundary_rings:
        if len(ring) < 2:
            continue
        path = canvas.beginPath()
        first_x, first_y = transform.map_point(ring[0])
        path.moveTo(first_x, first_y)
        for point in ring[1:]:
            x, y = transform.map_point(point)
            path.lineTo(x, y)
        path.close()
        canvas.setStrokeColor(HexColor("#ffffff"))
        canvas.setLineWidth(config.boundary_casing_width)
        canvas.setLineJoin(1)
        canvas.setLineCap(1)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.setStrokeColor(HexColor(config.boundary_color))
        canvas.setLineWidth(config.boundary_width)
        canvas.setDash(6, 5)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.setDash()


def draw_geojson_layer(
    canvas: Canvas,
    transform: PageTransform,
    transformer: Transformer,
    geojson: dict,
    color: str,
    width: float,
) -> None:
    canvas.setStrokeColor(HexColor(color))
    canvas.setLineWidth(width)
    canvas.setLineJoin(1)
    canvas.setLineCap(1)
    canvas.setDash()

    for feature in geojson.get("features", []):
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            rings = coordinates
        elif geometry_type == "MultiPolygon":
            rings = [ring for polygon in coordinates for ring in polygon]
        else:
            continue

        for ring in rings:
            if len(ring) < 2:
                continue
            path = canvas.beginPath()
            first = transform.map_point(ProjectedPoint(*transformer.transform(ring[0][0], ring[0][1])))
            path.moveTo(*first)
            for lon, lat in ring[1:]:
                x, y = transform.map_point(ProjectedPoint(*transformer.transform(lon, lat)))
                path.lineTo(x, y)
            canvas.drawPath(path, stroke=1, fill=0)


def draw_admin_layers(canvas: Canvas, transform: PageTransform, transformer: Transformer, admin_layers: dict[str, dict]) -> None:
    for spec in sorted(ADMIN_LAYER_SPECS, key=lambda item: item["width"], reverse=True):
        geojson = admin_layers.get(spec["id"])
        if not geojson:
            continue
        draw_geojson_layer(canvas, transform, transformer, geojson, "#ffffff", spec["width"] + 0.8)
        draw_geojson_layer(canvas, transform, transformer, geojson, spec["color"], spec["width"])


def line_display_name(network: str, line_id: str) -> str:
    if network == "s-tog":
        return f"Line – S-tog {line_id}"
    return f"Line – {line_id}"


def line_label_candidates(record: LineRecord) -> list[tuple[ProjectedPoint, tuple[float, float]]]:
    fractions = [0.18, 0.32, 0.5, 0.68, 0.82]
    candidates: list[tuple[ProjectedPoint, tuple[float, float]]] = []
    for fraction in fractions:
        point, tangent = point_along_polyline(record.coordinates, fraction)
        angle = math.degrees(math.atan2(tangent[1], tangent[0]))
        candidates.append((point, tangent))
    return candidates


def draw_line_labels(canvas: Canvas, transform: PageTransform, line_records: list[LineRecord], station_records: list[StationRecord], config: PdfMapConfig, font_name: str) -> None:
    placer = LabelPlacer(transform, config)
    for station in station_records:
        x, y = transform.map_point(station.point)
        placer.reserve((x - 9, y - 9, x + 9, y + 9))

    grouped = line_groups(line_records)
    ordered_keys = [(network, line_id) for network in ("metro", "s-tog") for line_id in TRANSPORT_LINE_ORDER[network]]
    for network, line_id in ordered_keys:
        records = grouped.get((network, line_id))
        if not records:
            continue
        record = longest_record(records)
        text = line_display_name(network, line_id)
        font_size = config.label_font_size
        width = pdfmetrics.stringWidth(text, font_name, font_size) + config.label_padding_x * 2
        height = font_size * 1.25 + config.label_padding_y * 2
        found = False
        for point, tangent in line_label_candidates(record):
            angle = math.degrees(math.atan2(tangent[1], tangent[0]))
            centers = line_candidate_positions(point.x, point.y, angle, width, height, config.label_gap)
            for center_x, center_y in centers:
                box = (center_x - width / 2.0, center_y - height / 2.0, center_x + width / 2.0, center_y + height / 2.0)
                if not placer.is_free(box):
                    continue
                placer.reserve(box)
                draw_halo_text(canvas, center_x, center_y, text, font_name, font_size, record.color)
                found = True
                break
            if found:
                break
        if not found:
            point, tangent = point_along_polyline(record.coordinates, 0.5)
            angle = math.degrees(math.atan2(tangent[1], tangent[0]))
            center_x, center_y = line_candidate_positions(point.x, point.y, angle, width, height, config.label_gap)[0]
            draw_halo_text(canvas, center_x, center_y, text, font_name, font_size, record.color)
            placer.reserve((center_x - width / 2.0, center_y - height / 2.0, center_x + width / 2.0, center_y + height / 2.0))


def draw_halo_text(canvas: Canvas, center_x: float, center_y: float, text: str, font_name: str, font_size: float, text_color: str) -> None:
    canvas.setFont(font_name, font_size)
    canvas.setFillColor(white)
    for offset_x, offset_y in [(-0.35, 0), (0.35, 0), (0, -0.35), (0, 0.35)]:
        canvas.drawCentredString(center_x + offset_x, center_y + offset_y - font_size * 0.33, text)
    canvas.setFillColor(HexColor(text_color))
    canvas.drawCentredString(center_x, center_y - font_size * 0.33, text)


def draw_polyline(canvas: Canvas, transform: PageTransform, coordinates: list[ProjectedPoint], color: str, width: float) -> None:
    path = canvas.beginPath()
    first_x, first_y = transform.map_point(coordinates[0])
    path.moveTo(first_x, first_y)
    for point in coordinates[1:]:
        x, y = transform.map_point(point)
        path.lineTo(x, y)
    canvas.setStrokeColor(HexColor(color))
    canvas.setLineWidth(width)
    canvas.setLineJoin(1)
    canvas.setLineCap(1)
    canvas.drawPath(path, stroke=1, fill=0)


def draw_station(canvas: Canvas, transform: PageTransform, station: StationRecord, radius: float, stroke_width: float) -> None:
    x, y = transform.map_point(station.point)
    canvas.setFillColor(white)
    canvas.setStrokeColor(HexColor("#172033"))
    canvas.setLineWidth(stroke_width)
    canvas.circle(x, y, radius, stroke=1, fill=1)


def rectangles_intersect(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return not (
        left[2] <= right[0]
        or left[0] >= right[2]
        or left[3] <= right[1]
        or left[1] >= right[3]
    )


class LabelPlacer:
    def __init__(self, transform: PageTransform, config: PdfMapConfig):
        self.transform = transform
        self.config = config
        self.occupied: list[tuple[float, float, float, float]] = []

    def within_bounds(self, box: tuple[float, float, float, float]) -> bool:
        return (
            box[0] >= self.transform.offset_x
            and box[1] >= self.transform.offset_y
            and box[2] <= self.transform.offset_x + self.transform.bounds.width * self.transform.scale
            and box[3] <= self.transform.offset_y + self.transform.bounds.height * self.transform.scale
        )

    def is_free(self, box: tuple[float, float, float, float]) -> bool:
        padded = (
            box[0] - self.config.label_clearance,
            box[1] - self.config.label_clearance,
            box[2] + self.config.label_clearance,
            box[3] + self.config.label_clearance,
        )
        if not self.within_bounds(padded):
            return False
        return all(not rectangles_intersect(padded, other) for other in self.occupied)

    def reserve(self, box: tuple[float, float, float, float]) -> None:
        self.occupied.append(box)


def line_candidate_positions(
    center_x: float,
    center_y: float,
    angle_degrees: float,
    box_width: float,
    box_height: float,
    gap: float,
) -> list[tuple[float, float]]:
    angle = math.radians(angle_degrees)
    normal_x = -math.sin(angle)
    normal_y = math.cos(angle)
    tangent_x = math.cos(angle)
    tangent_y = math.sin(angle)
    offsets = [
        (normal_x, normal_y, 1.0),
        (-normal_x, -normal_y, 1.0),
        (normal_x + tangent_x * 0.12, normal_y + tangent_y * 0.12, 1.0),
        (-normal_x - tangent_x * 0.12, -normal_y - tangent_y * 0.12, 1.0),
    ]
    centers: list[tuple[float, float]] = []
    for offset_x, offset_y, multiplier in offsets:
        distance = gap + box_height / 2.0 * multiplier
        centers.append((center_x + offset_x * distance, center_y + offset_y * distance))
    return centers


def draw_transit_map(
    output_path: Path,
    boundary_geojson: dict,
    line_records: list[LineRecord],
    station_records: list[StationRecord],
    admin_layers: dict[str, dict],
    config: PdfMapConfig,
) -> None:
    combined_bounds = merge_bounds(None, [point for record in line_records for point in record.coordinates])
    combined_bounds = merge_bounds(combined_bounds, [station.point for station in station_records])
    boundary_rings = []
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    for ring in extract_boundary_rings(boundary_geojson):
        projected_ring = project_coordinates(ring, transformer)
        if len(projected_ring) >= 2:
            boundary_rings.append(projected_ring)
    if boundary_rings:
        boundary_points = [point for ring in boundary_rings for point in ring]
        render_bounds = merge_bounds(None, boundary_points)
    else:
        render_bounds = combined_bounds

    (page_width, page_height), padded_bounds, scale, offset_x, offset_y = orient_page(render_bounds, config)
    transform = make_transform(page_width, page_height, padded_bounds, scale, offset_x, offset_y)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output_path), pagesize=(page_width, page_height), pageCompression=1)
    canvas.setTitle("Copenhagen transit map")
    canvas.setAuthor("hide_and_seek")
    canvas.setSubject("Transit map with street background exported directly from GeoJSON")
    canvas.setCreator("hide_and_seek/scripts/generate_transit_map_pdf.py")

    canvas.setFillColor(white)
    canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)

    draw_tile_background(canvas, transform, config)

    draw_admin_layers(canvas, transform, transformer, admin_layers)

    for network in ("metro", "s-tog"):
        for line_id in TRANSPORT_LINE_ORDER[network]:
            matching = [record for record in line_records if record.network == network and record.line_id == line_id]
            for record in matching:
                if config.line_casing_width > 0:
                    draw_polyline(canvas, transform, record.coordinates, "#ffffff", config.line_casing_width)
                draw_polyline(canvas, transform, record.coordinates, record.color, config.line_width)

    for station in station_records:
        draw_station(canvas, transform, station, config.station_radius, config.station_stroke_width)

    draw_boundary(canvas, transform, boundary_rings, config)

    draw_line_labels(canvas, transform, line_records, station_records, config, choose_font())
    canvas.showPage()
    canvas.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=Path, default=DEFAULT_INPUT_LINES, help="Input transport-lines GeoJSON")
    parser.add_argument("--stations", type=Path, default=DEFAULT_INPUT_STATIONS, help="Input transport-stations GeoJSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF path")
    parser.add_argument("--orientation", choices=["auto", "portrait", "landscape"], default="auto", help="Page orientation")
    parser.add_argument("--margin", type=float, default=18.0, help="Page margin in points")
    parser.add_argument("--line-width", type=float, default=1.6, help="Transit line width in points")
    parser.add_argument("--line-casing-width", type=float, default=3.8, help="White casing width in points")
    parser.add_argument("--station-radius", type=float, default=1.85, help="Station marker radius in points")
    parser.add_argument("--background-zoom", type=int, default=14, help="Street background tile zoom level")
    parser.add_argument("--tile-url", type=str, default=DEFAULT_TILE_URL, help="Tile URL template with {z}, {x}, and {y}")
    parser.add_argument("--tile-cache-dir", type=Path, default=Path(".cache/transit-map/tiles"), help="Tile cache directory")
    parser.add_argument("--boundary", type=Path, default=DEFAULT_INPUT_BOUNDARY, help="Input boundary GeoJSON")
    parser.add_argument("--hide-admin-divisions", action="store_true", help="Omit administrative division layers from the map")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> PdfMapConfig:
    return PdfMapConfig(
        orientation=args.orientation,
        margin=args.margin,
        line_width=args.line_width,
        line_casing_width=args.line_casing_width,
        station_radius=args.station_radius,
        background_zoom=args.background_zoom,
        tile_url=args.tile_url,
        tile_cache_dir=args.tile_cache_dir,
    )


def main() -> None:
    args = parse_args()
    config = config_from_args(args)
    lines_geojson = load_geojson(args.lines)
    stations_geojson = load_geojson(args.stations)
    boundary_geojson = load_geojson(args.boundary)
    admin_layers = {} if args.hide_admin_divisions else {spec["id"]: load_geojson(spec["path"]) for spec in ADMIN_LAYER_SPECS}
    line_records, station_records, _bounds = build_render_data(lines_geojson, stations_geojson)
    draw_transit_map(args.output, boundary_geojson, line_records, station_records, admin_layers, config)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()