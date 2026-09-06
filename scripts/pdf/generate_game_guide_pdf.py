
#!/usr/bin/env python3
"""Generate a printable PDF quick-reference guide for the Copenhagen hide-and-seek game."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


TITLE = "Copenhagen Hide & Seek - Rules"


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


def build_story() -> list:
    story = [
        Paragraph(TITLE, styles["GuideTitle"]),
        Spacer(1, 4 * mm),
    ]
    story.extend(build_rule_sections())
    return story


def generate_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    generate_pdf(args.output)
    print(f"PDF generated: {args.output.resolve()}")


