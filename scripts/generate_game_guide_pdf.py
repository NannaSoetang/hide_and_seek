
#!/usr/bin/env python3
"""Generate a printable PDF quick-reference guide for the Copenhagen hide-and-seek game."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    Paragraph,
    PageBreak,
    SimpleDocTemplate,
    Spacer,
    BaseDocTemplate,
    Frame,
    PageTemplate,
)


TITLE = "Copenhagen Hide & Seek – Quick Reference Guide"

ROOT = Path(__file__).resolve().parents[1]
TRANSIT_LINES_PATH = ROOT / "web" / "src" / "transit-lines.json"
TRANSPORT_STATIONS_PATH = ROOT / "web" / "public" / "data" / "transport-stations.geojson"


def load_transit_line_catalog() -> list[str]:
    """Return the canonical transit-line names from the shared frontend metadata source."""
    data = json.loads(TRANSIT_LINES_PATH.read_text(encoding="utf-8"))
    return [str(entry["line"]) for entry in data]


def load_line_stops() -> dict[str, list[str]]:
    """Return station names for each line from the generated GeoJSON."""
    data = json.loads(TRANSPORT_STATIONS_PATH.read_text(encoding="utf-8"))
    lines_by_station: dict[str, list[str]] = {}

    for feature in data.get("features", []):
        properties = feature.get("properties") or {}
        station_name = str(properties.get("name") or "").strip()

        if not station_name:
            continue

        for line_name in properties.get("lines") or []:
            line_key = str(line_name).strip()

            if not line_key:
                continue

            lines_by_station.setdefault(line_key, [])

            if station_name not in lines_by_station[line_key]:
                lines_by_station[line_key].append(station_name)

    return lines_by_station


RULES = [
    (
        "Core setup",
        [
            "Small game. Hider team max 6 cards unless they have a power-up.",
            "If the hider exceeds their hand limit, they must immediately play or discard cards until they are back down to 6 cards, unless a power-up increases their hand limit.",
            "The hider receives the hider deck; the seekers receive the investigation book.",
            "Both sides should have access to the rules and carry at least two dice for game mechanics.",
            "The seekers must keep a location tracker active so the hider can follow their movements.",
        ],
    ),
    (
        "Hiding period",
        [
            "The hider has 30 minutes to reach their hiding location.",
            "During the hiding period, the hider may travel on foot and use approved public transit.",
            "The hider must finish the hiding period in the zone of a transit station or stop included on the game map.",
            "That station becomes the center of the hider's hiding zone.",
            "Once the hiding period ends, the hider must remain within the hiding zone for the rest of the round.",
        ],
    ),
    (
        "Hiding zone & endgame",
        [
            "Hide zone: 300 meters from the hider's station.",
            "Once seekers enter the hide zone and are no longer on transit, the endgame begins.",
            "Once the endgame begins, the hider may no longer move freely.",
            "The hider must stay in a publicly accessible hiding spot until found.",
            "In the endgame, the hider may be no more than 3 meters from a public pathway, road, or path.",
            "The hider is considered found when seekers are within 5 feet and have spotted them.",
            "If seekers are close but have not identified the hider, the hider has not yet been found.",
            "When the hider is found, stop the hiding clock and add all time-bonus cards in the hider's hand to their final hiding time.",
        ],
    ),
    (
        "Timing & question flow",
        [
            "Seekers may ask only one question at a time; the next question cannot be asked until the previous one has been answered.",
            "Normal question: 5 minutes.",
            "Photo question: 10 minutes.",
            "If a question is not answered within the allowed time, the hider's time is paused until the question is answered, and the hider does not draw cards for that question.",
            "The hider must answer questions truthfully and based on their current location.",
            "If a question cannot be answered because of the hider's movement restrictions, the valid answer is: 'I cannot answer this question.'",
            "Questions that have already been asked may be repeated, but the cost increases each time: 2× for the second asking, 3× for the third, 4× for the fourth, and so on.",
            "Repeated questions are resolved as separate draws at the multiplied cost; do not combine them into one larger draw.",
        ],
    ),
    (
        "Research & mapping",
        [
            "Google Maps must remain visible to the hider.",
            "Google Street View is not allowed.",
            "AI tools are not allowed.",
            "Other internet research is allowed unless a specific game rule prohibits it.",
            "Only game-approved transit and routes may be used.",
            "Use Google Maps distance measurement for distance questions.",
            "Treat places outside the game map as if they do not exist.",
            "When a question asks about the seekers' location, the seekers must drop a pin at the point where they were when the question was asked.",
            "Seekers should record useful information in the investigation book and on the game map.",
        ],
    ),
    (
        "Cards & rewards",
        [
            "Matching: draw 3, keep 1.",
            "Measuring: draw 3, keep 1.",
            "Radar: draw 2, keep 1.",
            "Thermometer: draw 2, keep 1.",
            "Photo: draw 1, keep 1.",
            "Cards are drawn after a question has been answered, according to the question category.",
            "The hider keeps cards until they are played or discarded.",
            "Multiple curses may be played, but only one curse can block questions or transport at a time.",
        ],
    ),
    (
        "Photo rules",
        [
            "Photo questions may be taken as soon as the hider reaches the endgame zone.",
            "Photos taken before the endgame cannot be used in the endgame.",
            "If the target is unavailable from the hider's current position, the answer is: 'I cannot answer this question.'",
            "EXAMPLE: For a wide-route photo, use the widest valid route in the entire endgame zone, not just the closest option.",
        ],
    ),
    (
        "Other rules",
        [
            "Administrative levels: Municipality, Constituency, Postcode, Church zone.",
            "The hider answer questions truthfully based on their own location; they have the 5 minutes to move so if they go over a border, answer and then go back it is a valid answer."
        ],
    ),
]


def build_rule_sections() -> list:
    story = []

    for title, bullets in RULES:
        story.append(
            Paragraph(
                title,
                styles["GuideSectionTitle"],
            )
        )

        story.append(
            ListFlowable(
                [
                    Paragraph(bullet, styles["GuideBodyText"])
                    for bullet in bullets
                ],
                bulletType="bullet",
                leftIndent=18,
                bulletFontName="Helvetica",
                bulletText="•",
            )
        )

        story.append(Spacer(1, 6 * mm))

    return story


def build_steps_story() -> list:
    """Build a compact, user-facing steps story with key actionable sections."""
    story = [
        Paragraph("Quick Steps", styles["GuideTitle"]),
        Spacer(1, 4 * mm),
    ]

    selected = {"Core setup", "Hiding period", "Timing & question flow", "Hiding zone & endgame", "Cards & rewards"}

    for title, bullets in RULES:
        if title not in selected:
            continue

        story.append(Paragraph(title, styles["GuideSectionTitle"]))
        story.append(
            ListFlowable(
                [Paragraph(bullet, styles["GuideBodyText"]) for bullet in bullets],
                bulletType="bullet",
                leftIndent=12,
                bulletFontName="Helvetica",
                bulletText="•",
            )
        )
        story.append(Spacer(1, 4 * mm))

    return story


def generate_steps_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    frame_width = (doc.width / 2.0) - (4 * mm)
    frame_height = doc.height
    frame1 = Frame(doc.leftMargin, doc.bottomMargin, frame_width, frame_height, id="col1")
    frame2 = Frame(doc.leftMargin + frame_width + 8 * mm, doc.bottomMargin, frame_width, frame_height, id="col2")
    doc.addPageTemplates([PageTemplate(id="TwoCol", frames=[frame1, frame2])])
    doc.build(build_steps_story())


def generate_rules_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story = [Paragraph(TITLE, styles["GuideTitle"]), Spacer(1, 4 * mm)]
    story.extend(build_rule_sections())
    doc.build(story)


def build_line_sections() -> list:
    story = []

    story.append(
        Paragraph(
            "Transit lines and stops",
            styles["GuideSectionTitle"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    stops_by_line = load_line_stops()

    for line_name in load_transit_line_catalog():
        stops = stops_by_line.get(line_name, [])

        if not stops:
            continue

        stops_text = "; ".join(stops)

        story.append(
            Paragraph(
                f"<b>{line_name}</b> — {len(stops)} stops",
                styles["GuideSubheading"],
            )
        )

        story.append(
            Paragraph(
                stops_text,
                styles["GuideBodyText"],
            )
        )

        story.append(Spacer(1, 4 * mm))

    return story


def build_story() -> list:
    story = [
        Paragraph(TITLE, styles["GuideTitle"]),
        Spacer(1, 4 * mm),
    ]

    story.extend(build_rule_sections())

    story.append(PageBreak())
    story.extend(build_line_sections())

    return story


def generate_pdf(output_path: Path, compact: bool = False) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if compact:
        doc = BaseDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=8 * mm,
            rightMargin=8 * mm,
            topMargin=8 * mm,
            bottomMargin=8 * mm,
        )

        frame_width = (doc.width / 2.0) - (4 * mm)
        frame_height = doc.height
        frame1 = Frame(doc.leftMargin, doc.bottomMargin, frame_width, frame_height, id="col1")
        frame2 = Frame(doc.leftMargin + frame_width + 8 * mm, doc.bottomMargin, frame_width, frame_height, id="col2")
        doc.addPageTemplates([PageTemplate(id="TwoCol", frames=[frame1, frame2])])
        doc.build(build_story())
    else:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
        )
        doc.build(build_story())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PDF quick-reference guide for the Copenhagen hide-and-seek game."
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/copenhagen-hide-and-seek-guide.pdf"),
        help="Where to save the generated PDF.",
    )
    parser.add_argument("--compact", action="store_true", help="Produce a compact, two-column one-page PDF (best-effort)")
    parser.add_argument("--steps-output", type=Path, help="Write a compact steps PDF to this path")
    parser.add_argument("--rules-output", type=Path, help="Write a rules-only PDF to this path")

    return parser.parse_args()


def create_styles() -> None:
    global styles

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="GuideTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=20,
            spaceAfter=6,
            alignment=1,
        )
    )

    styles.add(
        ParagraphStyle(
            name="GuideSectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            spaceBefore=6,
            spaceAfter=3,
            textColor=colors.HexColor("#1f2937"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="GuideSubheading",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            spaceBefore=2,
            spaceAfter=2,
        )
    )

    styles.add(
        ParagraphStyle(
            name="GuideBodyText",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10.5,
            spaceAfter=2,
        )
    )


if __name__ == "__main__":
    args = parse_args()
    create_styles()

    # Generate main guide (default)
    generate_pdf(args.output, compact=bool(getattr(args, "compact", False)))
    print(f"PDF generated: {args.output.resolve()}")

    # Optional separate outputs
    if getattr(args, "steps_output", None):
        generate_steps_pdf(args.steps_output)
        print(f"Steps PDF generated: {args.steps_output.resolve()}")

    if getattr(args, "rules_output", None):
        generate_rules_pdf(args.rules_output)
        print(f"Rules PDF generated: {args.rules_output.resolve()}")


