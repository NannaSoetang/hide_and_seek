import json
from pathlib import Path

from scripts.generate_game_guide_pdf import load_line_stops, load_transit_line_catalog


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_STATIONS = ROOT / "web" / "public" / "data" / "transport-stations.geojson"


def test_game_guide_uses_line_stops_from_generated_map_data():
    guide_lines = load_transit_line_catalog()
    generated = load_line_stops()
    map_stops = json.loads(TRANSPORT_STATIONS.read_text(encoding="utf-8"))

    station_names_by_line = {}
    for feature in map_stops.get("features", []):
        props = feature.get("properties") or {}
        for line in props.get("lines") or []:
            station_names_by_line.setdefault(str(line), [])
            name = str(props.get("name") or "").strip()
            if name and name not in station_names_by_line[str(line)]:
                station_names_by_line[str(line)].append(name)

    assert guide_lines
    for line in guide_lines:
        assert generated.get(line) == station_names_by_line.get(line, [])
