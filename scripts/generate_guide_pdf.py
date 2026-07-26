#!/usr/bin/env python3
"""Generate an editorial-style PDF guide for the hide_and_seek game."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


BASE_DIR = Path(__file__).resolve().parents[1]
LINES_PATH = BASE_DIR / "web/public/data/transport-lines.geojson"
STATIONS_PATH = BASE_DIR / "web/public/data/transport-stations.geojson"
DEFAULT_OUTPUT = BASE_DIR / "guide-onepager.pdf"

METRO_META = {
    "M1": {"title": "M1", "route": "Vanløse – Vestamager", "color": "#00a650", "network": "Metro"},
    "M2": {"title": "M2", "route": "Vanløse – Lufthavnen", "color": "#f5c400", "network": "Metro"},
    "M3": {"title": "M3", "route": "Cityringen", "color": "#e03b3b", "network": "Metro"},
    "M4": {"title": "M4", "route": "Orientkaj – København Syd", "color": "#0072bc", "network": "Metro"},
}

STOG_META = {
    "A": {"title": "A-linje", "route": "Hillerød – Køge (Tilladt Lyngby - Vallensbæk)", "color": "#1f4e9e", "network": "S-tog"},
    "B": {"title": "B-linje", "route": "Farum – Høje Taastrup (Tilladt Buddinge - Glostrup)", "color": "#2f9e44", "network": "S-tog"},
    "C": {"title": "C-linje", "route": "Klampenborg – Frederikssund (Tilladt Klampenborg - Herlev)", "color": "#f28e2b", "network": "S-tog"},
    "F": {"title": "F-linje", "route": "Hellerup – København Syd", "color": "#f2a900", "network": "S-tog"},
}

RULES = [
    "Gemmerne må højst have 6 kort på hånden.",
    "I transportsektionen må kun Metro og S-tog bruges.",
    "AI og Google Street View må ikke bruges.",
]

GAME_PHASES = [
    "Forberedelse: Hvert hold får 15 minutter, før de skal gemme sig.",
    "Gemmefase: Gemmerne har 30 minutter til at vælge en station og blive inden for 500 meter af den.",
    "Slutfase: Når søgerne kommer ind i gemmezonen, må gemmerne ikke flytte sig mere.",
    "Sejr: Holdet med den længste samlede gemmetid efter begge runder vinder.",
]

QUESTION_EXPLANATIONS = [
    (
        "Hvad er en administrativ inddeling?",
        "En administrativ inddeling er et geografisk område som kommune, opstillingskreds, postnummer eller sogn.",
    ),
    (
        "Hvordan besvares spørgsmål?",
        "Spørgsmål besvares ærligt inden for svarfristen, og svaret gælder stadig, hvis I krydser en grænse efter, at spørgsmålet er stillet.",
    ),
    (
        "Hvordan bruges Google Maps og Google Street View korrekt?",
        "Google Maps må bruges til at måle afstand i fugleflugt, men Google Street View må ikke bruges.",
    ),
]

QUESTION_TYPES = [
    "Matching, nærmest og samme bruges til korte ja/nej-vurderinger.",
    "Måling bruges, når afstanden eller relationen skal oplyses.",
    "Termometer og radar bruges til henholdsvis retning og nærhed.",
    "Billedspørgsmål har længere svarfrist og kræver et konkret foto.",
]

EXAMPLE_QUESTIONS = [
    "Har vi samme nærmeste punkt?",
    "Hvem af os er tættest på rådhuset?",
    "Hvad er afstanden i fugleflugt til station X?",
    "Er vi blevet varmere eller koldere siden sidste måling?",
    "Tag et billede fra din station.",
]


@dataclass(frozen=True)
class LineSpec:
    network: str
    line_id: str
    title: str
    route: str
    color: str
    stations: list[tuple[str, bool]]


class TransitLineDiagram(Flowable):
    def __init__(self, width: float, color: str, stations: list[tuple[str, bool]]):
        super().__init__()
        self.width = width
        self.color = HexColor(color)
        self.stations = stations
        self.height = 31 * mm

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.width = min(self.width, availWidth)
        return self.width, self.height

    def _label_lines(self, name: str) -> list[str]:
        words = name.split()
        if len(words) <= 2 or len(name) <= 14:
            return [name]

        halfway = max(1, len(words) // 2)
        first = " ".join(words[:halfway]).strip()
        second = " ".join(words[halfway:]).strip()
        return [first, second] if second else [name]

    def draw(self) -> None:
        canvas = self.canv
        n = len(self.stations)
        left = 9 * mm
        right = self.width - 9 * mm
        center_y = self.height / 2
        step = 0 if n < 2 else (right - left) / (n - 1)

        canvas.saveState()
        canvas.setStrokeColor(self.color)
        canvas.setLineWidth(3.2)
        canvas.setLineCap(1)
        canvas.line(left, center_y, right, center_y)

        for index, (name, is_transfer) in enumerate(self.stations):
            x = left + step * index if n > 1 else (left + right) / 2
            label_lines = self._label_lines(name)
            label_color = HexColor("#835900") if is_transfer else HexColor("#213a5f")
            font_name = "Helvetica-Bold" if is_transfer else "Helvetica"
            label_y = center_y + 7.4 * mm if index % 2 == 0 else center_y - 9.4 * mm
            label_step = 4.4 * mm

            canvas.setFillColor(colors.white)
            canvas.setStrokeColor(self.color)
            canvas.setLineWidth(1.4)
            canvas.circle(x, center_y, 2.7 * mm, stroke=1, fill=1)

            canvas.setFillColor(label_color)
            canvas.setFont(font_name, 7.2)
            if index % 2 == 0:
                baseline = label_y
            else:
                baseline = label_y + (len(label_lines) - 1) * label_step

            for line_index, line in enumerate(label_lines):
                y = baseline - line_index * label_step
                canvas.drawCentredString(x, y, line)

        canvas.restoreState()


def choose_font() -> str:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    for font_path in candidates:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("GuideSans", str(font_path)))
            return "GuideSans"
    return "Helvetica"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    return json.loads(path.read_text())


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def clean_station_name(name: str) -> str:
    return re.sub(r"\s*\(Metro\)\s*", "", str(name or "")).strip()


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def line_length(coords: list[tuple[float, float]]) -> float:
    return sum(distance(coords[i - 1], coords[i]) for i in range(1, len(coords)))


def best_line_coordinates(features: list[dict], line_id: str) -> list[tuple[float, float]]:
    candidates = [
        feature.get("geometry", {}).get("coordinates", [])
        for feature in features
        if feature.get("properties", {}).get("line") == line_id
    ]
    candidates = [coords for coords in candidates if isinstance(coords, list) and len(coords) > 1]
    return max(candidates, key=line_length) if candidates else []


def station_measure_on_line(station_coord: tuple[float, float], line_coords: list[tuple[float, float]]) -> float:
    if len(line_coords) < 2:
        return float("inf")

    cumulative = 0.0
    best_distance = float("inf")
    best_measure = float("inf")
    for index in range(1, len(line_coords)):
        a = line_coords[index - 1]
        b = line_coords[index]
        abx = b[0] - a[0]
        aby = b[1] - a[1]
        apx = station_coord[0] - a[0]
        apy = station_coord[1] - a[1]
        denom = abx * abx + aby * aby
        t = 0.0 if denom == 0 else max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
        proj = (a[0] + abx * t, a[1] + aby * t)
        dist = distance(station_coord, proj)
        if dist < best_distance:
            best_distance = dist
            best_measure = cumulative + distance(a, proj)
        cumulative += distance(a, b)
    return best_measure


def line_stations(stations: list[dict], line_id: str) -> list[dict]:
    return [feature for feature in stations if line_id in (feature.get("properties", {}).get("lines") or [])]


def transfer_names(metro_stations: list[dict], stog_stations: list[dict]) -> set[str]:
    metro = {clean_station_name(feature.get("properties", {}).get("name", "")).casefold() for feature in metro_stations}
    stog = {clean_station_name(feature.get("properties", {}).get("name", "")).casefold() for feature in stog_stations}
    return metro & stog


def ordered_station_names(stations: list[dict], line_coords: list[tuple[float, float]], transfers: set[str]) -> list[tuple[str, bool]]:
    ordered = sorted(
        stations,
        key=lambda feature: station_measure_on_line(tuple(feature.get("geometry", {}).get("coordinates", [0.0, 0.0])), line_coords),
    )
    names: list[tuple[str, bool]] = []
    for feature in ordered:
        name = clean_station_name(feature.get("properties", {}).get("name", ""))
        if not name:
            continue
        names.append((name, name.casefold() in transfers))
    return names


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def bullet_paragraph(text: str, style: ParagraphStyle, indent: int = 0) -> Paragraph:
    prefix = "&nbsp;" * (indent * 4)
    return Paragraph(f"{prefix}• {text}", style)


def box(width: float, title: str, body: list, title_style: ParagraphStyle, accent: str, fill: str) -> Table:
    content = [paragraph(title, title_style), Spacer(1, 1.3 * mm)]
    content.extend(body)
    table = Table([[content]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("LINEBEFORE", (0, 0), (-1, -1), 4, HexColor(accent)),
                ("BOX", (0, 0), (-1, -1), 0.7, HexColor("#d8e0ea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def compact_card(width: float, title: str, body: list, title_style: ParagraphStyle, accent: str, fill: str) -> Table:
    return box(width, title, body, title_style, accent, fill)


def card_grid(cards: list[Table], cols: int, width: float, gap: float) -> Table:
    if len(cards) % cols != 0:
        raise ValueError("Card count must be divisible by column count")
    col_width = (width - gap * (cols - 1)) / cols
    rows = [cards[index : index + cols] for index in range(0, len(cards), cols)]
    table = Table(rows, colWidths=[col_width] * cols, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), gap),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), gap),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def build_line_specs() -> list[LineSpec]:
    lines_geojson = load_json(LINES_PATH)
    stations_geojson = load_json(STATIONS_PATH)
    metro_stations = [feature for feature in stations_geojson.get("features", []) if "metro" in feature.get("properties", {}).get("networks", [])]
    stog_stations = [feature for feature in stations_geojson.get("features", []) if "s-tog" in feature.get("properties", {}).get("networks", [])]
    transfers = transfer_names(metro_stations, stog_stations)

    specs: list[LineSpec] = []
    for line_id in ["M1", "M2", "M3", "M4"]:
        meta = METRO_META[line_id]
        line_coords = best_line_coordinates(lines_geojson.get("features", []), line_id)
        specs.append(
            LineSpec(
                network="Metro",
                line_id=line_id,
                title=meta["title"],
                route=meta["route"],
                color=meta["color"],
                stations=ordered_station_names(line_stations(metro_stations, line_id), line_coords, transfers),
            )
        )
    for line_id in ["A", "B", "C", "F"]:
        meta = STOG_META[line_id]
        line_coords = best_line_coordinates(lines_geojson.get("features", []), line_id)
        specs.append(
            LineSpec(
                network="S-tog",
                line_id=line_id,
                title=meta["title"],
                route=meta["route"],
                color=meta["color"],
                stations=ordered_station_names(line_stations(stog_stations, line_id), line_coords, transfers),
            )
        )
    return specs


def build_title_page(width: float, section_style: ParagraphStyle, body_style: ParagraphStyle, title_style: ParagraphStyle, subtitle_style: ParagraphStyle) -> list:
    story: list = []
    story.append(paragraph("Spilguide", title_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(paragraph("Et kort, struktureret regelhæfte til Hide & Seek med stationer, regler og spørgsmål samlet i ét rent layout.", subtitle_style))
    story.append(Spacer(1, 5 * mm))

    story.append(
        box(
            width,
            "Hvad finder du her?",
            [
                paragraph("Stationerne er vist som enkle linjediagrammer, så ruter og stop er lette at skimme.", body_style),
                Spacer(1, 1.2 * mm),
                paragraph("Reglerne er samlet i en kort, dansk form uden gentagelser.", body_style),
                Spacer(1, 1.2 * mm),
                paragraph("Spørgsmålene forklarer begreberne og viser den forventede form og sværhedsgrad.", body_style),
            ],
            section_style,
            "#213a5f",
            "#fbfcfe",
        )
    )
    story.append(Spacer(1, 4 * mm))
    return story


def build_allowed_station_page(width: float, section_style: ParagraphStyle, body_style: ParagraphStyle, card_style: ParagraphStyle) -> list:
    story: list = []
    story.append(paragraph("Tilladte stationer", section_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(paragraph("Hver linje er vist som et enkelt diagram med farvet linje og stationer placeret i rækkefølge.", body_style))
    story.append(Spacer(1, 4 * mm))

    specs = build_line_specs()
    cards = []
    for spec in specs:
        cards.append(
            compact_card(
                width / 2 - 2.5 * mm,
                f"<font color='{spec.color}'><b>{escape_html(spec.title)}</b></font> <font color='#738195'>{escape_html(spec.network)}</font>",
                [
                    paragraph(f"<b>{escape_html(spec.route)}</b>", body_style),
                    Spacer(1, 1.5 * mm),
                    TransitLineDiagram(width / 2 - 7 * mm, spec.color, spec.stations),
                ],
                card_style,
                spec.color,
                "#ffffff",
            )
        )
    story.append(card_grid(cards, 2, width, 4 * mm))
    return story


def build_rules_page(width: float, section_style: ParagraphStyle, body_style: ParagraphStyle, card_style: ParagraphStyle) -> list:
    story: list = []
    story.append(paragraph("Regler", section_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(paragraph("Reglerne er skrevet kort og samler kun det, spillerne skal huske undervejs.", body_style))
    story.append(Spacer(1, 3 * mm))
    story.append(
        box(
            width,
            "Regler",
            [paragraph(text, body_style) for text in RULES],
            card_style,
            "#c0392b",
            "#fff8f5",
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(
        box(
            width,
            "Spilfaser",
            [paragraph(f"{index + 1}. {text}", body_style) for index, text in enumerate(GAME_PHASES)],
            card_style,
            "#2f9e44",
            "#f6fff8",
        )
    )
    return story


def build_questions_page(width: float, section_style: ParagraphStyle, body_style: ParagraphStyle, card_style: ParagraphStyle) -> list:
    story: list = []
    story.append(paragraph("Spørgsmål", section_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(paragraph("Spørgsmålsafsnittet forklarer begreberne kort og viser både spørgsmålstyper og eksempler.", body_style))
    story.append(Spacer(1, 4 * mm))

    note_cards = [
        box(
            width / 3 - 2.5 * mm,
            title,
            [paragraph(text, body_style)],
            card_style,
            "#835900",
            "#fffaf0",
        )
        for title, text in QUESTION_EXPLANATIONS
    ]
    story.append(card_grid(note_cards, 3, width, 4 * mm))
    story.append(Spacer(1, 4 * mm))

    question_cards = [
        box(width / 2 - 2.5 * mm, "Spørgsmålstyper", [paragraph(text, body_style) for text in QUESTION_TYPES], card_style, "#213a5f", "#fbfcfe"),
        box(width / 2 - 2.5 * mm, "Eksempelspørgsmål", [paragraph(text, body_style) for text in EXAMPLE_QUESTIONS], card_style, "#213a5f", "#fbfcfe"),
    ]
    story.append(card_grid(question_cards, 2, width, 4 * mm))
    return story


def draw_page_frame(canvas: Canvas, doc: SimpleDocTemplate, label: str, font_name: str) -> None:
    canvas.saveState()
    page_width, page_height = A4
    left = doc.leftMargin
    right = page_width - doc.rightMargin
    top = page_height - 10 * mm
    bottom = 9 * mm

    canvas.setFillColor(HexColor("#172033"))
    canvas.setFont(font_name, 8.4)
    canvas.drawString(left, top, "Hide and Seek guide")
    canvas.setFillColor(HexColor("#5b6c80"))
    canvas.setFont(font_name, 7.1)
    canvas.drawRightString(right, top, label)

    canvas.setStrokeColor(HexColor("#d8e0ea"))
    canvas.setLineWidth(0.8)
    canvas.line(left, top - 3.5 * mm, right, top - 3.5 * mm)

    canvas.setFillColor(HexColor("#5b6c80"))
    canvas.setFont(font_name, 7.0)
    canvas.drawRightString(right, bottom, f"Side {canvas.getPageNumber()}")
    canvas.restoreState()


def build_pdf(output_path: Path) -> None:
    font_name = choose_font()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "GuideTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=24,
        leading=26,
        textColor=HexColor("#172033"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    subtitle_style = ParagraphStyle(
        "GuideSubtitle",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.0,
        leading=11.0,
        textColor=HexColor("#4d6077"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=16,
        leading=18,
        textColor=HexColor("#213a5f"),
        spaceAfter=0,
    )
    card_style = ParagraphStyle(
        "CardTitle",
        parent=styles["Heading3"],
        fontName=font_name,
        fontSize=10.5,
        leading=12.0,
        textColor=HexColor("#172033"),
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        "GuideBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8.2,
        leading=10.0,
        textColor=HexColor("#27384f"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=20 * mm,
        bottomMargin=14 * mm,
        title="Spilguide",
        author="hide_and_seek",
        subject="Editorial rulebook-style guide for the hide_and_seek game",
        creator="hide_and_seek/scripts/generate_guide_pdf.py",
    )

    story: list = []
    story.extend(build_title_page(doc.width, section_style, body_style, title_style, subtitle_style))
    story.append(PageBreak())
    story.extend(build_allowed_station_page(doc.width, section_style, body_style, card_style))
    story.append(PageBreak())
    story.extend(build_rules_page(doc.width, section_style, body_style, card_style))
    story.append(PageBreak())
    story.extend(build_questions_page(doc.width, section_style, body_style, card_style))

    doc.build(
        story,
        onFirstPage=lambda canvas, document: draw_page_frame(canvas, document, "Overview", font_name),
        onLaterPages=lambda canvas, document: draw_page_frame(canvas, document, "Rulebook", font_name),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_pdf(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()