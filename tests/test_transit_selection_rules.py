import io
import zipfile
from pathlib import Path

from shapely.geometry import Polygon

from scripts.build_data import clip_route_to_zone_shapes, load_selected_stop_rows, load_transit_config, load_transit_rules, matches_transit_rule, merge_route_segments, select_best_route_shape


def test_matches_transit_rule_handles_all_rule_classes():
    assert matches_transit_rule("M1", {"type": "metro"}) is True
    assert matches_transit_rule("A", {"type": "s-train"}, "109") is True
    assert matches_transit_rule("A", {"type": "s-train"}, "3") is False
    assert matches_transit_rule("150S", {"type": "bus", "pattern": "[digit]S"}) is True
    assert matches_transit_rule("500S", {"type": "bus", "pattern": "[digit]S"}) is False
    assert matches_transit_rule("5C", {"type": "bus", "pattern": "[digit]C"}) is True
    assert matches_transit_rule("78", {"type": "bus", "pattern": "[digit]S"}) is False
    assert matches_transit_rule("M1", {"type": "bus", "pattern": "[digit]S"}) is False


def test_load_transit_rules_supports_yaml_config_file(tmp_path):
    yaml_path = tmp_path / "transit_rules.yaml"
    yaml_path.write_text(
        'transit:\n  - type: metro\n  - type: bus\n    pattern: "[digit]S"\n\nzones:\n  - "1"\n  - "2"\n',
        encoding="utf-8",
    )
    config = load_transit_config(yaml_path)
    assert config["transit"] == [
        {"type": "metro"},
        {"type": "bus", "pattern": "[digit]S"},
    ]
    assert config["zones"] == ["1", "2"]
    assert load_transit_rules(yaml_path) == config["transit"]


def test_default_transit_rules_include_generic_bus_discovery():
    bus_rules = [rule for rule in load_transit_rules() if rule.get("type") == "bus"]
    assert bus_rules
    assert all("pattern" in rule for rule in bus_rules)

    for rule in bus_rules:
        pattern = rule["pattern"]
        route_name = "150S" if "S" in pattern.upper() else "5C" if "C" in pattern.upper() else "1A"
        assert matches_transit_rule(route_name, rule) is True

    assert not any(matches_transit_rule("78", rule) for rule in bus_rules)
    assert not any(matches_transit_rule("4", rule) for rule in bus_rules)
    assert not any(matches_transit_rule("M1", rule) for rule in bus_rules)


def test_load_transit_config_supports_service_day_and_time_window():
    yaml_path = Path("/tmp/transit_rules_service_window.yaml")
    yaml_path.write_text(
        'service:\n'
        '  day: saturday\n'
        '  start_time: "11:00"\n'
        '  end_time: "16:00"\n\n'
        'transit:\n'
        '  - type: metro\n\n'
        'zones:\n'
        '  - "1"\n',
        encoding="utf-8",
    )

    config = load_transit_config(yaml_path)

    assert config["service"] == {
        "day": "saturday",
        "start_time": "11:00",
        "end_time": "16:00",
    }
    assert config["zones"] == ["1"]


def test_load_selected_stop_rows_respects_zone_filter_for_missing_zone_metadata():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,zone_id\n"
            "s1,In zone 1,55.68,12.57,1\n"
            "s2,Missing zone,55.69,12.58,\n"
            "s3,Wrong zone,55.70,12.59,2\n",
        )

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue()), mode="r") as archive:
        rows = load_selected_stop_rows(archive, {"r1": {"s1", "s2", "s3"}}, allowed_zones={"1"}, allowed_zone_shapes=None)

    assert set(rows) == {"s1"}


def test_clip_route_to_zone_shapes_keeps_only_zone_segment():
    zone = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    coords = [[-1, 0.5], [0.25, 0.5], [0.75, 0.5], [2, 0.5]]

    clipped = clip_route_to_zone_shapes(coords, [zone])

    assert clipped[0] == [0.0, 0.5]
    assert clipped[-1] == [1.0, 0.5]
    assert len(clipped) >= 2


def test_merge_route_segments_connects_nearby_fragments():
    segments = [
        [[12.45, 55.70], [12.46, 55.70]],
        [[12.4602, 55.70], [12.47, 55.70]],
    ]

    merged = merge_route_segments(segments)

    assert merged[0] == [12.45, 55.7]
    assert merged[-1] == [12.47, 55.7]
    assert len(merged) >= 3


def test_select_best_route_shape_prefers_coherent_path_over_backtracking():
    candidates = [
        [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
    ]

    best = select_best_route_shape(candidates)

    assert best == [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
