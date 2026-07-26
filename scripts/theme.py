"""Single source of truth for transit line and administrative layer styling.

Reads the same JSON definitions used by the web app (web/src/*.json) so the
interactive map and the generated PDFs stay in sync.
"""

from __future__ import annotations

import json
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "web" / "src"

TRANSIT_LINES: list[dict] = json.loads((_SRC_DIR / "transit-lines.json").read_text())
ADMIN_LAYERS: list[dict] = json.loads((_SRC_DIR / "admin-layers.json").read_text())

LINE_COLORS: dict[str, str] = {line["line"]: line["color"] for line in TRANSIT_LINES}


def lines_for_network(network: str) -> list[dict]:
    return [line for line in TRANSIT_LINES if line["network"] == network]
