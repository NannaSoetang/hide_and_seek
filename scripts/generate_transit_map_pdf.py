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
from shapely.geometry import Point, Polygon

from theme import ADMIN_LAYERS, LINE_COLORS, lines_for_network


TRANSPORT_LINE_ORDER = {
    network: [line["line"] for line in lines_for_network(network)]
    for network in ("metro", "s-tog")
}

ADMIN_LAYER_WIDTHS = {
    "kommuner": 2.6,
    "opstillingskredse": 2.2,
    "postomraader": 1.8,
    "sogne": 1.6,
}

ADMIN_LAYER_SPECS = [
    {
        "id": layer["id"],
        "path": Path("web/public/data") / layer["file"],
        "color": layer["color"],
        "width": ADMIN_LAYER_WIDTHS[layer["id"]],
    }
    for layer in ADMIN_LAYERS
]

DEFAULT_INPUT_LINES = Path("web/public/data/transport-lines.geojson")
DEFAULT_INPUT_STATIONS = Path("web/public/data/transport-stations.geojson")
DEFAULT_INPUT_BOUNDARY = Path("web/public/data/boundary.geojson")
DEFAULT_MAPS_DIR = Path("output/maps")
DEFAULT_OUTPUT = DEFAULT_MAPS_DIR / "transit-map.pdf"
DEFAULT_MAP_SET_OUTPUT = DEFAULT_MAPS_DIR / "maps.pdf"

WEB_MERCATOR = "EPSG:3857"
WGS84 = "EPSG:4326"
ETRS89_UTM32 = "EPSG:25832"
TILE_SIZE = 256
ORIGIN_SHIFT = 20037508.342789244
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TITLE_BAND_HEIGHT = 24.0
SCALE_BAND_HEIGHT = 58.0
BUFFER_RADIUS_METERS = 500.0
BUFFER_PALETTE = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#000000",
    "#F0E442",
)

MAP_SPECS = (
    ("kort", "Kort", None, False),
    ("kommunegraenser", "Kommunegrænser", "kommuner", False),
    ("sogne", "Sogne", "sogne", False),
    ("opstillingskredse", "Opstillingskredse", "opstillingskredse", False),
    ("postomraader", "Postområder", "postomraader", False),
    ("stationer-500m", "500 meter fra stationer", None, True),
)


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
class StationBuffer:
    station_name: str
    center_utm: ProjectedPoint
    geometry_utm: Polygon
    ring_web_mercator: list[ProjectedPoint]
    color: str


@dataclass(frozen=True)
class ScaleInfo:
    meters_per_point: float
    meters_per_centimeter: float
    representative_fraction: int

    @property
    def centimeter_text(self) -> str:
        rounded_meters = int(round(self.meters_per_centimeter / 10.0) * 10)
        return f"1 cm på kortet svarer til ca. {rounded_meters:,} m".replace(",", ".")

    @property
    def ratio_text(self) -> str:
        rounded_ratio = int(round(self.representative_fraction / 1000.0) * 1000)
        return f"Ca. 1:{rounded_ratio:,}".replace(",", ".")


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
        available_height = page_height - 2 * config.margin - TITLE_BAND_HEIGHT - SCALE_BAND_HEIGHT
        scale = min(available_width / padded_bounds.width, available_height / padded_bounds.height)
        used_width = padded_bounds.width * scale
        used_height = padded_bounds.height * scale
        offset_x = config.margin + (available_width - used_width) / 2.0
        offset_y = config.margin + SCALE_BAND_HEIGHT + (available_height - used_height) / 2.0
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


def draw_admin_layer(
    canvas: Canvas,
    transform: PageTransform,
    transformer: Transformer,
    admin_layers: dict[str, dict],
    active_layer_id: str | None,
) -> None:
    spec = next((item for item in ADMIN_LAYER_SPECS if item["id"] == active_layer_id), None)
    if spec is None:
        return
    geojson = admin_layers.get(spec["id"])
    if not geojson:
        return
    draw_geojson_layer(canvas, transform, transformer, geojson, "#ffffff", spec["width"] + 0.8)
    draw_geojson_layer(canvas, transform, transformer, geojson, spec["color"], spec["width"])


def station_centers_utm(station_records: list[StationRecord]) -> list[ProjectedPoint]:
    transformer = Transformer.from_crs(WEB_MERCATOR, ETRS89_UTM32, always_xy=True)
    return [ProjectedPoint(*transformer.transform(station.point.x, station.point.y)) for station in station_records]


def color_station_graph(centers: list[ProjectedPoint]) -> list[int]:
    adjacency = [set() for _ in centers]
    for left_index, left in enumerate(centers):
        for right_index in range(left_index + 1, len(centers)):
            right = centers[right_index]
            if math.hypot(right.x - left.x, right.y - left.y) < BUFFER_RADIUS_METERS * 2:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    colors = [-1] * len(centers)
    for station_index in sorted(range(len(centers)), key=lambda index: (-len(adjacency[index]), index)):
        used = {colors[neighbor] for neighbor in adjacency[station_index] if colors[neighbor] >= 0}
        color_index = next((index for index in range(len(BUFFER_PALETTE)) if index not in used), None)
        if color_index is None:
            raise ValueError("The station overlap graph requires more colors than BUFFER_PALETTE provides")
        colors[station_index] = color_index
    return colors


def build_station_buffers(station_records: list[StationRecord]) -> list[StationBuffer]:
    ordered = sorted(station_records, key=lambda station: (station.name, station.point.x, station.point.y))
    centers = station_centers_utm(ordered)
    color_indexes = color_station_graph(centers)
    to_web_mercator = Transformer.from_crs(ETRS89_UTM32, WEB_MERCATOR, always_xy=True)
    buffers = []
    for station, center, color_index in zip(ordered, centers, color_indexes):
        geometry_utm = Point(center.x, center.y).buffer(BUFFER_RADIUS_METERS, quad_segs=128)
        ring_web_mercator = [
            ProjectedPoint(*to_web_mercator.transform(x, y))
            for x, y in geometry_utm.exterior.coords
        ]
        buffers.append(
            StationBuffer(
                station_name=station.name,
                center_utm=center,
                geometry_utm=geometry_utm,
                ring_web_mercator=ring_web_mercator,
                color=BUFFER_PALETTE[color_index],
            )
        )
    return buffers


def draw_station_buffers(canvas: Canvas, transform: PageTransform, station_buffers: list[StationBuffer]) -> None:
    for station_buffer in station_buffers:
        path = canvas.beginPath()
        first_x, first_y = transform.map_point(station_buffer.ring_web_mercator[0])
        path.moveTo(first_x, first_y)
        for point in station_buffer.ring_web_mercator[1:]:
            path.lineTo(*transform.map_point(point))
        path.close()
        canvas.saveState()
        canvas.setStrokeColor(HexColor(station_buffer.color))
        canvas.setStrokeAlpha(0.95)
        canvas.setLineWidth(1.5)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()


def calculate_scale_info(transform: PageTransform) -> ScaleInfo:
    to_utm = Transformer.from_crs(WEB_MERCATOR, ETRS89_UTM32, always_xy=True)
    center_y = (transform.bounds.min_y + transform.bounds.max_y) / 2.0
    left = ProjectedPoint(*to_utm.transform(transform.bounds.min_x, center_y))
    right = ProjectedPoint(*to_utm.transform(transform.bounds.max_x, center_y))
    ground_width_meters = math.hypot(right.x - left.x, right.y - left.y)
    map_width_points = transform.bounds.width * transform.scale
    meters_per_point = ground_width_meters / map_width_points
    meters_per_centimeter = meters_per_point * (10 * mm)
    return ScaleInfo(
        meters_per_point=meters_per_point,
        meters_per_centimeter=meters_per_centimeter,
        representative_fraction=round(meters_per_centimeter * 100),
    )


def draw_title(canvas: Canvas, transform: PageTransform, title: str, font_name: str) -> None:
    canvas.setFillColor(HexColor("#172033"))
    canvas.setFont(font_name, 15)
    canvas.drawCentredString(transform.page_width / 2.0, transform.page_height - 10.5 * mm, title)


def draw_scale(canvas: Canvas, transform: PageTransform, scale_info: ScaleInfo, font_name: str) -> None:
    panel_x = transform.offset_x
    panel_y = transform.offset_y - SCALE_BAND_HEIGHT + 6.0
    panel_width = transform.bounds.width * transform.scale
    panel_height = SCALE_BAND_HEIGHT - 12.0
    canvas.setFillColor(white)
    canvas.setStrokeColor(HexColor("#cbd2d9"))
    canvas.setLineWidth(0.6)
    canvas.rect(panel_x, panel_y, panel_width, panel_height, stroke=1, fill=1)

    x = panel_x + 12.0
    y = panel_y + 22.0
    bar_height = 7.0
    distances = (0.0, 500.0, 1000.0, 2000.0)
    canvas.setStrokeColor(HexColor("#172033"))
    canvas.setLineWidth(1.0)
    for segment_index, (start, end) in enumerate(zip(distances, distances[1:])):
        segment_x = x + start / scale_info.meters_per_point
        segment_width = (end - start) / scale_info.meters_per_point
        canvas.setFillColor(HexColor("#172033") if segment_index % 2 == 0 else white)
        canvas.rect(segment_x, y, segment_width, bar_height, stroke=1, fill=1)

    canvas.setFillColor(HexColor("#172033"))
    canvas.setFont(font_name, 8.2)
    labels = ((0.0, "0", 10.0), (500.0, "500 m", -10.0), (1000.0, "1 km", 10.0), (2000.0, "2 km", -10.0))
    for distance, label, y_offset in labels:
        label_x = x + distance / scale_info.meters_per_point
        canvas.drawCentredString(label_x, y + y_offset, label)

    details_x = x + 2000.0 / scale_info.meters_per_point + 24.0
    canvas.setFont(font_name, 8.5)
    canvas.drawString(details_x, y + 7.0, scale_info.centimeter_text)
    canvas.setFont(font_name, 8.0)
    canvas.drawString(details_x, y - 4.0, scale_info.ratio_text)
    canvas.setFont(font_name, 7.2)
    canvas.setFillColor(HexColor("#4a5568"))
    canvas.drawRightString(panel_x + panel_width - 10.0, panel_y + 7.0, "Målestok gælder ved udskrift i 100 %")


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


def build_page_transform(boundary_geojson: dict, config: PdfMapConfig) -> PageTransform:
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    boundary_rings = [project_coordinates(ring, transformer) for ring in extract_boundary_rings(boundary_geojson)]
    boundary_points = [point for ring in boundary_rings for point in ring]
    if not boundary_points:
        raise ValueError("No geometry found in the boundary dataset")
    render_bounds = merge_bounds(None, boundary_points)
    (page_width, page_height), padded_bounds, scale, offset_x, offset_y = orient_page(render_bounds, config)
    return make_transform(page_width, page_height, padded_bounds, scale, offset_x, offset_y)


def render_map_page(
    canvas: Canvas,
    title: str,
    transform: PageTransform,
    line_records: list[LineRecord],
    station_records: list[StationRecord],
    boundary_rings: list[list[ProjectedPoint]],
    admin_layers: dict[str, dict],
    config: PdfMapConfig,
    active_admin_layer: str | None = None,
    station_buffers: list[StationBuffer] | None = None,
) -> None:
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    font_name = choose_font()

    canvas.setFillColor(white)
    canvas.rect(0, 0, transform.page_width, transform.page_height, stroke=0, fill=1)
    draw_title(canvas, transform, title, font_name)
    draw_scale(canvas, transform, calculate_scale_info(transform), font_name)

    canvas.saveState()
    clip_path = canvas.beginPath()
    clip_path.rect(
        transform.offset_x,
        transform.offset_y,
        transform.bounds.width * transform.scale,
        transform.bounds.height * transform.scale,
    )
    canvas.clipPath(clip_path, stroke=0, fill=0)
    draw_tile_background(canvas, transform, config)
    draw_admin_layer(canvas, transform, transformer, admin_layers, active_admin_layer)
    if station_buffers:
        draw_station_buffers(canvas, transform, station_buffers)

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
    draw_line_labels(canvas, transform, line_records, station_records, config, font_name)
    canvas.restoreState()
    canvas.showPage()


def configure_canvas(canvas: Canvas) -> None:
    canvas.setTitle("København kortsæt")
    canvas.setAuthor("hide_and_seek")
    canvas.setSubject("Printklare kort over Københavns transportnet")
    canvas.setCreator("hide_and_seek/scripts/generate_transit_map_pdf.py")


def draw_transit_map(
    output_path: Path,
    boundary_geojson: dict,
    line_records: list[LineRecord],
    station_records: list[StationRecord],
    admin_layers: dict[str, dict],
    config: PdfMapConfig,
    active_admin_layer: str | None = None,
) -> None:
    transform = build_page_transform(boundary_geojson, config)
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    boundary_rings = [project_coordinates(ring, transformer) for ring in extract_boundary_rings(boundary_geojson)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output_path), pagesize=(transform.page_width, transform.page_height), pageCompression=1)
    configure_canvas(canvas)
    render_map_page(
        canvas,
        "Kort",
        transform,
        line_records,
        station_records,
        boundary_rings,
        admin_layers,
        config,
        active_admin_layer=active_admin_layer,
    )
    canvas.save()


def draw_all_maps(
    combined_output: Path,
    output_dir: Path,
    boundary_geojson: dict,
    line_records: list[LineRecord],
    station_records: list[StationRecord],
    admin_layers: dict[str, dict],
    config: PdfMapConfig,
) -> ScaleInfo:
    transform = build_page_transform(boundary_geojson, config)
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    boundary_rings = [project_coordinates(ring, transformer) for ring in extract_boundary_rings(boundary_geojson)]
    station_buffers = build_station_buffers(station_records)
    combined_output.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_canvas = Canvas(
        str(combined_output),
        pagesize=(transform.page_width, transform.page_height),
        pageCompression=1,
    )
    configure_canvas(combined_canvas)
    for filename, title, admin_layer, show_buffers in MAP_SPECS:
        page_buffers = station_buffers if show_buffers else None
        render_map_page(
            combined_canvas,
            title,
            transform,
            line_records,
            station_records,
            boundary_rings,
            admin_layers,
            config,
            active_admin_layer=admin_layer,
            station_buffers=page_buffers,
        )

        page_path = output_dir / f"{filename}.pdf"
        page_canvas = Canvas(
            str(page_path),
            pagesize=(transform.page_width, transform.page_height),
            pageCompression=1,
        )
        configure_canvas(page_canvas)
        render_map_page(
            page_canvas,
            title,
            transform,
            line_records,
            station_records,
            boundary_rings,
            admin_layers,
            config,
            active_admin_layer=admin_layer,
            station_buffers=page_buffers,
        )
        page_canvas.save()
        print(f"Wrote {page_path}")

    combined_canvas.save()
    return calculate_scale_info(transform)


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
    parser.add_argument("--admin-layer", choices=[spec["id"] for spec in ADMIN_LAYER_SPECS], help="Administrative layer for a single map")
    parser.add_argument("--all-maps", action="store_true", help="Build maps.pdf and all six individual map PDFs")
    parser.add_argument("--maps-output", type=Path, default=DEFAULT_MAP_SET_OUTPUT, help="Combined six-page PDF path")
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR, help="Directory for individual map PDFs")
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
    if args.all_maps:
        scale_info = draw_all_maps(
            args.maps_output,
            args.maps_dir,
            boundary_geojson,
            line_records,
            station_records,
            admin_layers,
            config,
        )
        print(f"Wrote {args.maps_output}")
        print(f"Scale: {scale_info.centimeter_text}; {scale_info.ratio_text}")
    else:
        active_admin_layer = None if args.hide_admin_divisions else args.admin_layer
        draw_transit_map(
            args.output,
            boundary_geojson,
            line_records,
            station_records,
            admin_layers,
            config,
            active_admin_layer=active_admin_layer,
        )
        print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()