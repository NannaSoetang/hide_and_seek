#!/usr/bin/env python3
"""Generate a compact one-page PDF for the hide_and_seek guide."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from pyproj import Transformer
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


BASE_DIR = Path(__file__).resolve().parents[1]
LINES_PATH = BASE_DIR / "web/public/data/transport-lines.geojson"
STATIONS_PATH = BASE_DIR / "web/public/data/transport-stations.geojson"
GUIDE_PATH = BASE_DIR / "web/guide.html"
DEFAULT_OUTPUT = BASE_DIR / "guide-onepager.pdf"

WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"

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


@dataclass(frozen=True)
class GuideStation:
    name: str
    point: tuple[float, float]
    lines: tuple[str, ...]


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


def clean_station_name(name: str) -> str:
    return re.sub(r"\s*\(Metro\)\s*", "", str(name or "")).strip()


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.hypot(dx, dy)


def line_length(coords: list[tuple[float, float]]) -> float:
    return sum(distance(coords[i - 1], coords[i]) for i in range(1, len(coords)))


def best_line_coordinates(features: list[dict], line_id: str) -> list[tuple[float, float]]:
    candidates = [
        feature.get("geometry", {}).get("coordinates", [])
        for feature in features
        if feature.get("properties", {}).get("line") == line_id
    ]
    candidates = [coords for coords in candidates if isinstance(coords, list) and len(coords) > 1]
    if not candidates:
        return []
    return max(candidates, key=line_length)


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


def ordered_station_names(stations: list[dict], line_coords: list[tuple[float, float]], transfers: set[str]) -> str:
    ordered = sorted(
        stations,
        key=lambda feature: station_measure_on_line(tuple(feature.get("geometry", {}).get("coordinates", [0.0, 0.0])), line_coords),
    )
    names: list[str] = []
    for feature in ordered:
        name = clean_station_name(feature.get("properties", {}).get("name", ""))
        if not name:
            continue
        display = escape(name)
        if name.casefold() in transfers:
            display = f'<font color="#835900"><b>{display}</b></font>'
        names.append(display)
    return ", ".join(names)


def parse_guide_sections() -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
    text = GUIDE_PATH.read_text()

    rules = [
        (
            "Retningslinjer",
            [
                "<b>Transport:</b> Der må kun benyttes Metro og S-tog.",
                "Busser, regionaltog, letbane, havnebusser og øvrige transportmidler må ikke anvendes.",
                "<b>Informationskilder:</b>",
                "Google Street View og AI må ikke anvendes.",
                "Alle øvrige informationskilder er tilladt.",
                "<b>Gemmernes spilkort:</b> Gemmerne må maksimalt have 6 kort på hånden.",
                "Hvis grænsen overskrides, skal de straks spille eller kassere kort, indtil de igen har maksimalt seks kort.",
            ],
        ),
        (
            "Faser af spillet",
            [
                "<b>Forberedelsesfase:</b> Hvert hold får 15 minutter inden de skal gemme sig.",
                "<b>Gemmefase:</b> Gemmerne har 30 minutter til at gemme sig, skal vælge en station og opholde sig inden for 500 meter af den valgte station.",
                "<b>Afslutningsfase:</b> Når søgerne kommer ind i gemmezonen, starter slutspillet. Fra dette tidspunkt må gemmerne ikke længere flytte sig og skal blive på ét endeligt gemmested, maksimalt 3 meter fra en offentlig vej.",
                "<b>Vinder:</b> Begge hold spiller som gemmere. Det hold der samlet har den længste gemmetid efter begge runder vinder.",
            ],
        ),
    ]

    questions = [
        (
            "Noter",
            [
                "<b>Administrative inddelinger</b>",
                "1. Admin division = Kommune",
                "2. Admin division = Opstillingskreds",
                "3. Admin division = Postnumre",
                "4. Admin division = Sogn",
                "<b>Ærlige svar og spørgsmål</b>",
                "Alle spørgsmål skal besvares ærligt.",
                "Svarfristen er 5 minutter for normale spørgsmål og 10 minutter for billedspørgsmål.",
                "Hvis gemmerne flytter sig over en administrativ grænse (kommune, sogn, postområde eller opstillingskreds) efter spørgsmålet er stillet, er svaret stadig gyldigt.",
                "Spørgsmål må kun handle om noget inden for spillezonen. Man kan derfor ikke spørge, hvem der er tættest på Storebæltsbroen da den ligger uden for området.",
                "Når et spørgsmål først er blevet stillet, kan det ikke anvendes igen medmindre søgerne betaler prisen endnu en gang.",
                "<b>Måling i Google Maps</b>",
                "Brug Google Maps til at måle distance. Målingen laves i fugleflugt.",
                "Når du dropper en pin, vises funktionen \"mål distance\".",
            ],
        ),
        (
            "1. Matching / Nærmest / Samme (Du har 5 minutter)",
            [
                "<b>Beskrivelse:</b> Bruges til at afgøre om I matcher samme referencepunkt eller hvem der er nærmest.",
                "<b>Eksempel:</b> \"Har vi samme nærmeste punkt?\" / \"Er du nærmere end mig?\"",
            ],
        ),
        (
            "2. Measuring / Måling (Du har 5 minutter)",
            [
                "<b>Beskrivelse:</b> Bruges når regelsættet giver et målingsspørgsmål, hvor afstand eller relation skal oplyses.",
                "<b>Eksempel:</b> \"Mål afstanden til punkt X og oplys resultatet.\"",
            ],
        ),
        (
            "3. Thermometer / Termometer (Du har 5 minutter)",
            [
                "<b>Beskrivelse:</b> Bruges til varmere/koldere-feedback efter bevægelse, så man kan justere retning.",
                "<b>Eksempel:</b> \"Er vi blevet varmere eller koldere siden sidste måling?\"",
            ],
        ),
        (
            "4. Radar (Du har 5 minutter)",
            [
                "<b>Beskrivelse:</b> Bruges til et hurtigt nærheds-tjek mellem holdene.",
                "<b>Eksempel:</b> \"Er du inden for 2 km af mig?\"",
            ],
        ),
        (
            "5. Tentacle (Ikke bruges i small)",
            [""],
        ),
        (
            "6. Photos / Billede (Du har 10 minutter)",
            [
                "<b>Beskrivelse:</b> Kræver billede fra bestemt sted og har 10 minutters svarfrist.",
                "<b>Eksempel:</b> \"Tag et billede fra din station.\"",
                "Hvis et spørgsmål kræver et billede fra et sted, som gemmerne ikke kan komme til uden at forlade deres zone, er \"Jeg kan ikke besvare spørgsmålet\" et gyldigt svar.",
                "Gemmerne trækker stadig et kort.",
                "Det anbefales at tage relevante billeder på forhånd for at få større fleksibilitet senere.",
            ],
        ),
    ]

    if "Spilleregler" not in text or "Spørgsmålstyper" not in text:
        raise RuntimeError("Guide HTML content missing expected sections")

    return rules, questions


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def section_block(title: str, body_lines: list[str], title_style: ParagraphStyle, body_style: ParagraphStyle) -> list:
    flowables = [paragraph(escape(title), title_style)]
    for line in body_lines:
        if not line:
            flowables.append(Spacer(1, 2))
            continue
        flowables.append(paragraph(line, body_style))
    return flowables


def build_output(path: Path) -> None:
    font_name = choose_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GuideTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=17,
        leading=19,
        textColor=HexColor("#172033"),
        alignment=TA_LEFT,
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "GuideSubtitle",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=7.2,
        leading=8.1,
        textColor=HexColor("#445a77"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=8.9,
        leading=10.0,
        textColor=HexColor("#1f3f69"),
        spaceBefore=2,
        spaceAfter=1,
    )
    subsection_title_style = ParagraphStyle(
        "SubsectionTitle",
        parent=styles["Heading3"],
        fontName=font_name,
        fontSize=7.8,
        leading=8.8,
        textColor=HexColor("#203a5d"),
        spaceBefore=1,
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        "GuideBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=5.55,
        leading=6.4,
        textColor=HexColor("#24364f"),
        spaceAfter=0,
    )
    body_bold_style = ParagraphStyle(
        "GuideBodyBold",
        parent=body_style,
        fontName=font_name,
        fontSize=5.55,
        leading=6.4,
    )

    lines_geojson = load_json(LINES_PATH)
    stations_geojson = load_json(STATIONS_PATH)
    rules, questions = parse_guide_sections()

    metro_lines = [lines_geojson["features"] for _ in [0]][0]
    metro_stations = [feature for feature in stations_geojson.get("features", []) if "metro" in feature.get("properties", {}).get("networks", [])]
    stog_stations = [feature for feature in stations_geojson.get("features", []) if "s-tog" in feature.get("properties", {}).get("networks", [])]
    transfers = transfer_names(metro_stations, stog_stations)
    transformer = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)

    left_flowables: list = [paragraph("Tilladte stationer", section_title_style), paragraph("Alle stationer, grupperet pr. linje i rejseretning.", body_style)]
    for header, meta_map, line_ids, stations_source in [
        ("Metro", METRO_META, ["M1", "M2", "M3", "M4"], metro_stations),
        ("S-tog", STOG_META, ["A", "B", "C", "F"], stog_stations),
    ]:
        left_flowables.append(paragraph(escape(header), subsection_title_style))
        for line_id in line_ids:
            meta = meta_map[line_id]
            line_coords = best_line_coordinates(lines_geojson.get("features", []), line_id)
            stations = line_stations(stations_source, line_id)
            stations_text = ordered_station_names(stations, line_coords, transfers)
            left_flowables.append(
                paragraph(
                    f'<font color="{meta["color"]}"><b>{escape(meta["title"])}:</b></font> '
                    f'<font color="#314760">{escape(meta["route"])}</font>',
                    body_bold_style,
                )
            )
            left_flowables.append(paragraph(stations_text or "&nbsp;", body_style))

    right_flowables: list = [paragraph("Spilleregler", section_title_style), paragraph("Vi spiller Small Game.", body_style)]
    right_flowables.append(paragraph('<font color="#1f3f69"><b>Quick start guide</b></font>', subsection_title_style))
    right_flowables.append(paragraph('https://www.lifack.ch/docs/quick_start_guide/', body_style))
    for title, body_lines in rules:
        right_flowables.append(paragraph(escape(title), subsection_title_style))
        for line in body_lines:
            right_flowables.append(paragraph(line, body_style))

    right_flowables.append(Spacer(1, 3))
    right_flowables.append(paragraph("Spørgsmål", section_title_style))
    for title, body_lines in questions:
        right_flowables.append(paragraph(escape(title), subsection_title_style))
        if len(body_lines) == 1 and not body_lines[0]:
            right_flowables.append(paragraph("Ikke bruges i small.", body_style))
            continue
        for line in body_lines:
            right_flowables.append(paragraph(line, body_style))

    page_width, page_height = landscape(A4)
    margin = 10 * mm
    title_height = 19 * mm
    gutter = 7 * mm
    usable_width = page_width - 2 * margin - gutter
    left_width = usable_width * 0.53
    right_width = usable_width - left_width
    body_height = page_height - 2 * margin - title_height

    canvas = Canvas(str(path), pagesize=(page_width, page_height), pageCompression=1)
    canvas.setTitle("Hide and Seek guide")
    canvas.setAuthor("hide_and_seek")
    canvas.setSubject("One-page guide summary with allowed stations, rules, and questions")
    canvas.setCreator("hide_and_seek/scripts/generate_guide_pdf.py")
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)

    from reportlab.platypus import Frame

    title_block = [
        paragraph("Spilguide", title_style),
        paragraph("Tilladte stationer, spilleregler og spørgsmålstyper samlet på én side.", subtitle_style),
    ]
    title_frame = Frame(margin, page_height - margin - title_height, page_width - 2 * margin, title_height, leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0, showBoundary=0)
    left_frame = Frame(margin, margin, left_width, body_height, leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0, showBoundary=0)
    right_frame = Frame(margin + left_width + gutter, margin, right_width, body_height, leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0, showBoundary=0)

    title_frame.addFromList(title_block, canvas)
    left_frame.addFromList(left_flowables, canvas)
    right_frame.addFromList(right_flowables, canvas)
    canvas.showPage()
    canvas.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_output(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()