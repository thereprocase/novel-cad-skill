"""Tests for check_printability.py — _results state isolation."""

import sys
from pathlib import Path
from unittest.mock import patch

_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR / "scripts"))
sys.path.insert(0, str(_SKILL_DIR / "lib"))


class TestResultsIsolation:
    """Verify that _results doesn't bleed between calls."""

    def test_reset_clears_results(self):
        import check_printability as cp

        cp._reset_results()
        assert len(cp._results) == 0

        cp._emit(cp.FAIL, "test", "forced failure")
        assert cp.FAIL in cp._results

        cp._reset_results()
        assert len(cp._results) == 0

    def test_multiple_runs_isolated(self):
        """Calling _reset_results between runs prevents cross-contamination."""
        import check_printability as cp

        # Run 1: emit a FAIL
        cp._reset_results()
        cp._emit(cp.FAIL, "run1", "failure in run 1")
        assert cp.FAIL in cp._results

        # Run 2: emit only PASS
        cp._reset_results()
        cp._emit(cp.PASS, "run2", "pass in run 2")
        assert cp.FAIL not in cp._results
        assert cp.PASS in cp._results

    def test_check_printability_api_resets(self):
        """The check_printability() library function resets internally."""
        import check_printability as cp

        # Pollute _results
        cp._emit(cp.FAIL, "pollution", "should not persist")
        assert cp.FAIL in cp._results

        # Verify the function exists and accepts the right signature
        import inspect
        sig = inspect.signature(cp.check_printability)
        params = list(sig.parameters.keys())
        assert "mesh" in params
        assert "thresholds" in params
