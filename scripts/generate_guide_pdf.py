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

from theme import TRANSIT_LINES


BASE_DIR = Path(__file__).resolve().parents[1]
LINES_PATH = BASE_DIR / "web/public/data/transport-lines.geojson"
STATIONS_PATH = BASE_DIR / "web/public/data/transport-stations.geojson"
DEFAULT_OUTPUT = BASE_DIR / "guide-onepager.pdf"

GAME_PHASES = [
    ("Forberedelsesfase", "Hvert hold får 15 minutter til at forberede sig, før de gemmer sig."),
    ("Spillet", "Gemmerne vælger en station og skal blive inden for 500 meter af den. De har 30 minutter til at nå frem til deres zone."),
    ("Slutfase", "Når søgerne kommer inden for 500 meter af den valgte station, må gemmerne ikke længere flytte sig. Gemmerne kan hele tiden følge søgerne på Google Maps."),
    ("Vinder", "Holdet med den længste samlede gemmetid efter begge runder vinder."),
]

RULE_GROUPS = [
    (
        "Spil og bevægelse",
        [
            "Vi spiller Small Game.",
            "Du må kun bruge offentlig transport: Metro og S-tog.",
            "Når gemmerne har valgt deres gemmested, skal de være højst 3 meter fra en offentlig vej eller sti.",
        ],
    ),
    (
        "Spørgsmål",
        [
            "Svar altid ærligt. I må bruge hele svartiden på at flytte jer. Svaret skal tage udgangspunkt i jeres placering på det tidspunkt, hvor I svarer, medmindre spørgsmålet specifikt handler om gemmestationens placering. Svaret gælder fortsat, hvis I krydser en grænse, efter at I har svaret.",
            "Hver gang der stilles et spørgsmål med en beslutning, der vedrører søgerne, skal søgerne sende deres position.",
            "Hvis man bruger det samme spørgsmål i samme kategori flere gange, stiger betalingen. Anden gang fordobles den: Koster spørgsmålet normalt »træk 2, behold 1«, må gemmerne i stedet trække 4 og beholde 2. Tredje gang tredobles betalingen osv.",
            "Du kan ikke stille et nyt spørgsmål, før du har modtaget svar på det forrige.",
            "Hvis spørgsmålet ikke kan besvares inden for svartiden, sættes gemmernes tid på pause, indtil spørgsmålet er besvaret. Imens må de ikke trække kort fra dækket.",
        ],
    ),
    (
        "Kort",
        [
            "Gemmerne må højst have 6 kort på hånden, medmindre de har en powerup. Hvis de efter at have trukket har mere end 6 kort, skal de spille eller smide kort, indtil de har 6.",
            "Du kan spille flere curses, men kun én curse, der forhindrer søgerne i at handle, må være aktiv ad gangen. Det gælder både spørgsmål og brug af transport.",
        ],
    ),
    (
        "Værktøjer og områder",
        [
            "Google Maps er det nemmeste værktøj til at måle afstand — brug «Mål distance», så får du afstanden i fugleflugt.",
            "AI og Google Street View må ikke bruges.",
            "En administrativ inddeling er et af følgende områder: 1. kommune, 2. opstillingskreds, 3. postnummer eller 4. sogn.",
            "Man kan ikke bruge elementer, der ligger uden for spilområdet, i sine spørgsmål, f.eks. Billund Lufthavn.",
        ],
    ),
]

# Hver type følges direkte af sit eksempel: (type, forklaring, eksempel, valgfri note).
# Small Game — tentakelspørgsmål bruges ikke.
QUESTION_TYPES = [
    ("Matchning", "«Er jeres nærmeste ___ det samme som vores?» Svar: ja eller nej.", "Er jeres nærmeste station den samme som vores?", None),
    ("Måling", "«Sammenlignet med os, er I tættere på eller længere fra ___?» Svar: tættere eller længere.", "Sammenlignet med os, er I tættere på eller længere fra en kyst?", None),
    ("Radar", "«Er I inden for ___ fra os?» Svar: ja eller nej.", "Er I inden for 1 km fra os?", None),
    ("Termometer", "«Efter vi har bevæget os ___, er vi blevet varmere eller koldere?» Søgerne sender deres position, rejser afstanden og spørger så. Svar: varmere eller koldere.", "Efter vi har bevæget os 800 m, er vi varmere eller koldere?", None),
    (
        "Billede",
        "«Send os et billede af ___.» Gemmerne må tage billeder på forhånd, men billeder taget på forhånd må ikke bruges i slutfasen. Kan motivet ikke nås — især i slutfasen, eller hvis det ikke findes i området — svarer de «Det er ikke muligt».",
        "Send os et billede af den bredeste vej.",
        "(Bredeste vej referer til området inden for 500 m af gemmernes station, ikke sightline. Hvis der er flere veje med samme bredde, må gemmerne vælge hvilken som helst af dem.)",
    ),
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
        self.height = 19 * mm

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
        left = 5 * mm
        right = self.width - 5 * mm
        center_y = self.height / 2
        step = 0 if n < 2 else (right - left) / (n - 1)
        dot_radius = 1.5 * mm
        label_step = 3.1 * mm
        label_color = HexColor("#213a5f")

        canvas.saveState()
        canvas.setStrokeColor(self.color)
        canvas.setLineWidth(2.4)
        canvas.setLineCap(1)
        canvas.line(left, center_y, right, center_y)

        for index, (name, _is_transfer) in enumerate(self.stations):
            x = left + step * index if n > 1 else (left + right) / 2
            label_lines = self._label_lines(name)

            canvas.setFillColor(colors.white)
            canvas.setStrokeColor(self.color)
            canvas.setLineWidth(1.2)
            canvas.circle(x, center_y, dot_radius, stroke=1, fill=1)

            canvas.setFillColor(label_color)
            canvas.setFont("Helvetica", 6.4)
            if index % 2 == 0:
                nearest = center_y + dot_radius + 2.4 * mm
                for line_index, line in enumerate(label_lines):
                    y = nearest + (len(label_lines) - 1 - line_index) * label_step
                    canvas.drawCentredString(x, y, line)
            else:
                nearest = center_y - dot_radius - 3.0 * mm
                for line_index, line in enumerate(label_lines):
                    y = nearest - line_index * label_step
                    canvas.drawCentredString(x, y, line)

        canvas.restoreState()


def choose_font() -> str:
    candidates = [
        (
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/Library/Fonts/Arial.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ),
    ]
    for regular_path, bold_path in candidates:
        if not regular_path.exists():
            continue
        pdfmetrics.registerFont(TTFont("GuideSans", str(regular_path)))
        if bold_path.exists():
            pdfmetrics.registerFont(TTFont("GuideSans-Bold", str(bold_path)))
            pdfmetrics.registerFontFamily("GuideSans", normal="GuideSans", bold="GuideSans-Bold")
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


def two_columns(left: list, right: list, width: float, gap: float) -> Table:
    col_width = (width - gap) / 2
    table = Table([[left, right]], colWidths=[col_width, col_width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), gap),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
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
    stations_by_network = {"metro": metro_stations, "s-tog": stog_stations}

    specs: list[LineSpec] = []
    for meta in TRANSIT_LINES:
        line_coords = best_line_coordinates(lines_geojson.get("features", []), meta["line"])
        specs.append(
            LineSpec(
                network=meta["networkLabel"],
                line_id=meta["line"],
                title=meta["title"],
                route=meta["route"],
                color=meta["color"],
                stations=ordered_station_names(
                    line_stations(stations_by_network[meta["network"]], meta["line"]),
                    line_coords,
                    transfers,
                ),
            )
        )
    return specs


def build_reference_page(
    width: float,
    title_style: ParagraphStyle,
    subtitle_style: ParagraphStyle,
    section_style: ParagraphStyle,
    item_style: ParagraphStyle,
    type_style: ParagraphStyle,
    example_style: ParagraphStyle,
) -> list:
    story: list = []
    story.append(paragraph("Spilguide", title_style))
    story.append(paragraph("Hurtigguide — find svaret på få sekunder.", subtitle_style))
    story.append(Spacer(1, 5 * mm))

    left_column: list = [paragraph("Regler", section_style), Spacer(1, 2 * mm)]
    for group_name, rules in RULE_GROUPS:
        left_column.append(paragraph(f"<b>{escape_html(group_name)}</b>", type_style))
        for text in rules:
            left_column.append(bullet_paragraph(escape_html(text), item_style))
        left_column.append(Spacer(1, 1.5 * mm))

    right_column: list = [paragraph("Sådan spiller I", section_style), Spacer(1, 2 * mm)]
    for index, (label, text) in enumerate(GAME_PHASES):
        right_column.append(paragraph(f"<b>{index + 1}. {escape_html(label)}:</b>&nbsp;&nbsp;{escape_html(text)}", item_style))
    right_column.append(Spacer(1, 4 * mm))
    right_column.append(paragraph("Spørgsmålstyper", section_style))
    right_column.append(Spacer(1, 2 * mm))
    for name, explanation, example, note in QUESTION_TYPES:
        right_column.append(paragraph(f"<b>{escape_html(name)}</b>", type_style))
        right_column.append(paragraph(escape_html(explanation), item_style))
        right_column.append(paragraph(f"Eksempel: {escape_html(example)}", example_style))
        if note:
            right_column.append(paragraph(escape_html(note), example_style))
        right_column.append(Spacer(1, 2.4 * mm))

    story.append(two_columns(left_column, right_column, width, 8 * mm))
    return story


def build_transit_page(
    width: float,
    section_style: ParagraphStyle,
    subtitle_style: ParagraphStyle,
    network_style: ParagraphStyle,
    line_header_style: ParagraphStyle,
) -> list:
    story: list = []
    story.append(paragraph("Transitlinjer", section_style))
    story.append(paragraph("Du må kun rejse med Metro og S-tog. Følg hver linje fra ende til ende.", subtitle_style))
    story.append(Spacer(1, 3.5 * mm))

    specs = build_line_specs()
    current_network = None
    for spec in specs:
        if spec.network != current_network:
            if current_network is not None:
                story.append(Spacer(1, 1.5 * mm))
            story.append(paragraph(spec.network, network_style))
            story.append(Spacer(1, 1 * mm))
            current_network = spec.network

        header = (
            f"<font color='{spec.color}'><b>{escape_html(spec.title)}</b></font>"
            f"&nbsp;&nbsp;<font color='#5b6c80'>{escape_html(spec.route)}</font>"
        )
        story.append(paragraph(header, line_header_style))
        story.append(TransitLineDiagram(width, spec.color, spec.stations))
        story.append(Spacer(1, 1 * mm))

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
    canvas.drawString(left, top, "Spilguide")
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
        leading=11.5,
        textColor=HexColor("#4d6077"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        leading=15,
        textColor=HexColor("#213a5f"),
        spaceAfter=0,
    )
    network_style = ParagraphStyle(
        "NetworkTitle",
        parent=styles["Heading3"],
        fontName=font_name,
        fontSize=10.5,
        leading=12,
        textColor=HexColor("#5b6c80"),
        spaceAfter=0,
    )
    item_style = ParagraphStyle(
        "GuideItem",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8.6,
        leading=11.4,
        textColor=HexColor("#27384f"),
        alignment=TA_LEFT,
        spaceAfter=2,
    )
    type_style = ParagraphStyle(
        "QuestionType",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.4,
        leading=11.5,
        textColor=HexColor("#172033"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    example_style = ParagraphStyle(
        "QuestionExample",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8.4,
        leading=10.6,
        textColor=HexColor("#738195"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    line_header_style = ParagraphStyle(
        "LineHeader",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.2,
        leading=11,
        textColor=HexColor("#172033"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title="Spilguide",
        author="hide_and_seek",
        subject="Quick-reference guide for the hide_and_seek game",
        creator="hide_and_seek/scripts/generate_guide_pdf.py",
    )

    story: list = []
    story.extend(
        build_reference_page(
            doc.width,
            title_style,
            subtitle_style,
            section_style,
            item_style,
            type_style,
            example_style,
        )
    )
    story.append(PageBreak())
    story.extend(build_transit_page(doc.width, section_style, subtitle_style, network_style, line_header_style))

    doc.build(
        story,
        onFirstPage=lambda canvas, document: draw_page_frame(canvas, document, "Hurtigguide", font_name),
        onLaterPages=lambda canvas, document: draw_page_frame(canvas, document, "Transitlinjer", font_name),
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