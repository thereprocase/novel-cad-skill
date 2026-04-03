"""Tests for validate_geometry.py — pattern validation fix verification."""

import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "scripts"))
sys.path.insert(0, str(_SKILL_DIR / "lib"))


class TestPatternValidation:
    """Verify Bug 2 fix: pattern features use nested element keys."""

    def test_pattern_with_element_width_passes(self):
        """A pattern feature with element.width should PASS, not WARN."""
        from validate_geometry import check_features

        spec = {
            "overall_dimensions": {"width": 100, "depth": 50, "height": 20},
            "features": [{
                "type": "pattern",
                "name": "vent grid",
                "element": {"type": "slot", "width": 2.0, "length": 15.0},
                "arrangement": "linear",
                "count": 20,
                "pitch": 3.0,
                "tolerance": 0.3,
            }],
        }

        # check_features needs a shape, but pattern validation doesn't
        # actually probe geometry — it only reads the spec dict.
        # We can pass None since the pattern path doesn't use shape.
        results = check_features(None, spec)

        assert len(results) == 1
        r = results[0]
        assert r.passed is True
        assert not r.warn
        assert "20" in r.detail
        assert "2.00" in r.detail

    def test_pattern_with_element_diameter_passes(self):
        """Pattern with hole elements should use element.diameter."""
        from validate_geometry import check_features

        spec = {
            "overall_dimensions": {"width": 100, "depth": 50, "height": 20},
            "features": [{
                "type": "pattern",
                "name": "hole grid",
                "element": {"type": "hole", "diameter": 4.0},
                "arrangement": "grid",
                "count": 16,
                "tolerance": 0.3,
            }],
        }

        results = check_features(None, spec)
        assert len(results) == 1
        assert results[0].passed is True
        assert "4.00" in results[0].detail

    def test_pattern_missing_element_width_warns(self):
        """Pattern with no width or diameter in element should WARN."""
        from validate_geometry import check_features

        spec = {
            "overall_dimensions": {"width": 100, "depth": 50, "height": 20},
            "features": [{
                "type": "pattern",
                "name": "mystery grid",
                "element": {"type": "pocket"},
                "arrangement": "linear",
                "count": 5,
                "tolerance": 0.3,
            }],
        }

        results = check_features(None, spec)
        assert len(results) == 1
        assert results[0].warn is True

    def test_pattern_zero_count_warns(self):
        """Pattern with count=0 should WARN."""
        from validate_geometry import check_features

        spec = {
            "overall_dimensions": {"width": 100, "depth": 50, "height": 20},
            "features": [{
                "type": "pattern",
                "name": "empty grid",
                "element": {"type": "slot", "width": 2.0},
                "arrangement": "linear",
                "count": 0,
                "tolerance": 0.3,
            }],
        }

        results = check_features(None, spec)
        assert len(results) == 1
        assert results[0].warn is True

    def test_old_element_width_key_does_not_work(self):
        """The old bug: feat["element_width"] should NOT produce a PASS."""
        from validate_geometry import check_features

        spec = {
            "overall_dimensions": {"width": 100, "depth": 50, "height": 20},
            "features": [{
                "type": "pattern",
                "name": "broken pattern",
                "element_width": 2.0,  # OLD broken key — should be ignored
                "element": {"type": "slot"},  # no width in element
                "count": 10,
                "tolerance": 0.3,
            }],
        }

        results = check_features(None, spec)
        assert len(results) == 1
        # Should WARN because element has no width, even though element_width exists
        assert results[0].warn is True
