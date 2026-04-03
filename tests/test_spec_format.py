"""Tests for spec_format.py — round-trip create/write/load and validation."""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "lib"))

from spec_format import create_spec, write_spec, load_spec, validate_spec


class TestCreateSpec:
    def test_minimal_spec(self):
        spec = create_spec("test box", width=10, depth=20, height=30)
        assert spec["part_name"] == "test box"
        assert spec["overall_dimensions"]["width"] == 10.0
        assert spec["overall_dimensions"]["depth"] == 20.0
        assert spec["overall_dimensions"]["height"] == 30.0

    def test_defaults_applied(self):
        spec = create_spec("box", width=10, depth=10, height=10)
        assert spec["material"] == "PLA"
        assert spec["min_wall_mm"] == 1.2
        assert spec["engine"] == "build123d"
        assert spec["export_format"] == "3mf"
        assert spec["manifold_check"] is True
        assert spec["color"] == [0.7, 0.7, 0.7, 1.0]

    def test_custom_material(self):
        spec = create_spec("box", width=10, depth=10, height=10, material="TPU")
        assert spec["material"] == "TPU"
        assert spec["min_wall_mm"] == 3.0  # TPU default

    def test_invalid_material_raises(self):
        with pytest.raises(ValueError, match="not recognized"):
            create_spec("box", width=10, depth=10, height=10, material="NYLON")

    def test_zero_dimension_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            create_spec("box", width=0, depth=10, height=10)

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="part_name"):
            validate_spec({"overall_dimensions": {"width": 1, "depth": 1, "height": 1}})

    def test_warn_wall_above_min(self):
        spec = create_spec("box", width=10, depth=10, height=10,
                           min_wall_mm=1.2, warn_wall_mm=1.5)
        assert spec["warn_wall_mm"] == 1.5

    def test_warn_wall_below_min_raises(self):
        with pytest.raises(ValueError, match="warn_wall_mm"):
            create_spec("box", width=10, depth=10, height=10,
                        min_wall_mm=2.0, warn_wall_mm=1.5)

    def test_features_slot(self):
        spec = create_spec("tray", width=60, depth=40, height=25,
                           features=[{"type": "slot", "name": "card slot", "width": 2.0}])
        assert len(spec["features"]) == 1
        assert spec["features"][0]["type"] == "slot"
        assert spec["features"][0]["width"] == 2.0

    def test_features_hole(self):
        spec = create_spec("mount", width=30, depth=30, height=5,
                           features=[{"type": "hole", "name": "M4", "diameter": 4.3,
                                      "position": [10, 15]}])
        assert spec["features"][0]["diameter"] == 4.3
        assert spec["features"][0]["position"] == [10.0, 15.0]

    def test_features_pattern(self):
        spec = create_spec("vent", width=100, depth=50, height=20,
                           features=[{
                               "type": "pattern", "name": "vent grid",
                               "element": {"type": "slot", "width": 2.0, "length": 15.0},
                               "arrangement": "linear", "count": 20, "pitch": 3.0,
                               "position": [10, 20, 0], "direction": [1, 0, 0],
                           }])
        f = spec["features"][0]
        assert f["type"] == "pattern"
        assert f["element"]["type"] == "slot"
        assert f["element"]["width"] == 2.0
        assert f["count"] == 20

    def test_pattern_missing_element_raises(self):
        with pytest.raises(ValueError, match="element"):
            create_spec("x", width=10, depth=10, height=10,
                        features=[{"type": "pattern", "name": "p", "count": 5}])

    def test_pattern_invalid_element_type_raises(self):
        with pytest.raises(ValueError, match="not recognized"):
            create_spec("x", width=10, depth=10, height=10,
                        features=[{"type": "pattern", "name": "p", "count": 5,
                                   "element": {"type": "rail"}}])

    def test_components(self):
        spec = create_spec("tray", width=60, depth=40, height=25,
                           components=[{"name": "battery", "length": 50.5,
                                        "width": 14.5, "height": 14.5}])
        c = spec["components"][0]
        assert c["name"] == "battery"
        assert c["effective_clearance_mm"] == 0.3  # PLA default + 0.0

    def test_sub_phases(self):
        spec = create_spec("case", width=80, depth=50, height=30,
                           features=[
                               {"type": "hole", "name": "usb", "diameter": 5.0},
                               {"type": "hole", "name": "hdmi", "diameter": 8.0},
                           ],
                           sub_phases={"2a": ["usb"], "2b": ["hdmi"]})
        assert "2a" in spec["sub_phases"]

    def test_sub_phases_unknown_feature_raises(self):
        with pytest.raises(ValueError, match="unknown feature"):
            create_spec("case", width=80, depth=50, height=30,
                        features=[{"type": "hole", "name": "usb", "diameter": 5.0}],
                        sub_phases={"2a": ["nonexistent"]})


class TestWriteLoadRoundTrip:
    def test_round_trip(self, tmp_path):
        spec = create_spec("round trip box", width=42, depth=33, height=17,
                           material="PETG", min_wall_mm=2.0,
                           features=[{"type": "slot", "name": "sd", "width": 2.5}])
        step_path = str(tmp_path / "test.step")
        spec_path = write_spec(spec, step_path)

        assert os.path.exists(spec_path)
        assert spec_path.endswith(".spec.json")

        loaded = load_spec(spec_path)
        assert loaded["part_name"] == "round trip box"
        assert loaded["overall_dimensions"]["width"] == 42.0
        assert loaded["material"] == "PETG"
        assert loaded["features"][0]["width"] == 2.5

    def test_load_from_step_path(self, tmp_path):
        spec = create_spec("box", width=10, depth=10, height=10)
        step_path = str(tmp_path / "part.step")
        write_spec(spec, step_path)

        loaded = load_spec(step_path)
        assert loaded["part_name"] == "box"

    def test_load_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            load_spec("/nonexistent/path/foo.spec.json")

    def test_json_content_valid(self, tmp_path):
        spec = create_spec("json test", width=5, depth=5, height=5)
        path = write_spec(spec, str(tmp_path / "out.step"))
        with open(path, "r") as f:
            raw = json.load(f)
        assert raw["part_name"] == "json test"
        assert "overall_dimensions" in raw
