#!/usr/bin/env python3
"""
gate_enforcer.py -- Programmatic checkpoint enforcement for novel-cad-skill.

Persists phase approval state to a .gates.json file alongside the STEP export.
Raises RuntimeError if Claude attempts to move to the next phase without completing
the required validation + approval cycle.

State file location: <part_name>.gates.json in the current working directory,
or the directory of the STEP file if step_dir is provided.

Usage:
    from gate_enforcer import GateEnforcer

    gate = GateEnforcer("pi_case")
    gate.begin_phase("phase_1")
    # ... build geometry, run validators ...
    gate.record_validation("validate_geometry", passed=True)
    gate.record_validation("check_printability", passed=True)
    gate.record_validation("validate_manifold", passed=True)
    gate.record_cross_sections(["sec_1.png", "sec_2.png", "sec_3.png"])
    gate.request_approval("phase_1")   # prints GATE message; raises if not ready
    # ... user reviews and says "approved" ...
    gate.approve("phase_1", approved_by="user")
    gate.begin_phase("phase_2")        # raises if phase_1 not approved
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# Required validators that must pass before approval is granted
REQUIRED_VALIDATORS = (
    "validate_geometry",
    "check_printability",
    "validate_manifold",
)

# Minimum cross-section images required per phase
MIN_CROSS_SECTIONS = 3


class GateEnforcer:
    """
    Checkpoint state machine for the novel-cad-skill phase workflow.

    Phases must be completed in order. Each phase requires:
      - All REQUIRED_VALIDATORS recorded with passed=True
      - At least MIN_CROSS_SECTIONS cross-section images recorded
      - request_approval() called (prints GATE message)
      - approve() called after user confirms

    Sub-phases (e.g. "phase_2a", "phase_2b") follow the same rules.
    "phase_2b" requires "phase_2a" approved, etc.
    """

    def __init__(self, part_name: str, step_dir: str = None):
        """
        Args:
            part_name: Slug used in the .gates.json filename (no spaces).
            step_dir:  Directory to write the .gates.json file.
                       Defaults to the current working directory.
        """
        self.part_name = part_name
        base_dir = Path(step_dir) if step_dir else Path.cwd()
        self._state_path = base_dir / f"{part_name}.gates.json"
        self._state = self._load()

    # -- Persistence ----------------------------------------------------------

    def _load(self) -> dict:
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"part_name": self.part_name, "phases": {}}

    def _save(self) -> None:
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- Phase ordering -------------------------------------------------------

    def _phase_order_key(self, phase: str) -> tuple:
        """
        Return a sort key so phases compare correctly.

        "phase_1"  -> (1, 0, "")
        "phase_2"  -> (2, 0, "")
        "phase_2a" -> (2, 1, "a")
        "phase_2b" -> (2, 1, "b")
        "phase_3"  -> (3, 0, "")
        """
        import re
        m = re.match(r"phase_(\d+)([a-z]?)$", phase)
        if not m:
            return (999, 0, phase)
        num = int(m.group(1))
        sub = m.group(2)
        return (num, 1 if sub else 0, sub)

    def _predecessor(self, phase: str) -> str | None:
        """
        Return the phase that must be approved before `phase` can begin.
        Returns None for phase_1 (no predecessor).

        For phase_2b -> phase_2a.
        For phase_2a -> phase_1.
        For phase_3  -> latest approved phase_2x (or phase_2 if no sub-phases).
        """
        import re

        m = re.match(r"phase_(\d+)([a-z]?)$", phase)
        if not m:
            return None

        num = int(m.group(1))
        sub = m.group(2)

        if num == 1 and not sub:
            return None  # phase_1 has no predecessor

        if sub:
            # phase_2b -> phase_2a; phase_2a -> phase_1
            if sub == "a":
                return f"phase_{num - 1}"
            # find previous sub-phase letter
            prev_sub = chr(ord(sub) - 1)
            return f"phase_{num}{prev_sub}"

        # Non-sub phase like phase_3: predecessor is the last phase_2x or phase_2
        all_phases = sorted(self._state["phases"].keys(), key=self._phase_order_key)
        candidates = [p for p in all_phases
                      if self._phase_order_key(p) < self._phase_order_key(phase)]
        if not candidates:
            return None
        return candidates[-1]

    # -- Public API -----------------------------------------------------------

    def begin_phase(self, phase: str) -> None:
        """
        Start a new phase. Raises RuntimeError if the predecessor phase
        is not yet approved.
        """
        predecessor = self._predecessor(phase)
        if predecessor is not None:
            pred_data = self._state["phases"].get(predecessor, {})
            if pred_data.get("status") != "approved":
                raise RuntimeError(
                    f"[GateEnforcer] Cannot begin {phase}: "
                    f"{predecessor} has not been approved yet "
                    f"(status: {pred_data.get('status', 'not started')}). "
                    "Complete the approval cycle for the previous phase first."
                )

        if phase not in self._state["phases"]:
            self._state["phases"][phase] = {
                "status": "in_progress",
                "validations": {},
                "cross_sections": [],
                "started_at": self._now(),
            }
        else:
            self._state["phases"][phase]["status"] = "in_progress"

        self._save()
        print(f"[Gate] Phase {phase} started.")

    def record_validation(self, validator_name: str, passed: bool,
                          phase: str = None, details: str = "") -> None:
        """
        Record the result of a validation step.

        Args:
            validator_name: One of the REQUIRED_VALIDATORS names (or any string).
            passed:         True if the validator passed, False if it failed.
            phase:          Phase to record against. Defaults to current in-progress phase.
            details:        Optional detail string for the log.
        """
        phase = phase or self._current_phase()
        self._state["phases"][phase]["validations"][validator_name] = {
            "passed": passed,
            "timestamp": self._now(),
            "details": details,
        }
        status = "PASS" if passed else "FAIL"
        print(f"[Gate] Validation recorded: {validator_name} [{status}] for {phase}")
        self._save()

    def record_cross_sections(self, image_paths: list, phase: str = None) -> None:
        """
        Record cross-section image paths for the current phase.

        Args:
            image_paths: List of file paths to cross-section PNG images.
            phase:       Phase to record against. Defaults to current in-progress phase.
        """
        phase = phase or self._current_phase()
        self._state["phases"][phase]["cross_sections"] = [str(p) for p in image_paths]
        print(f"[Gate] Recorded {len(image_paths)} cross-section(s) for {phase}")
        self._save()

    def request_approval(self, phase: str = None) -> None:
        """
        Request user approval for a phase. Raises RuntimeError if the phase is
        not ready (validations not all passed, or insufficient cross-sections).

        When ready, prints the GATE message and sets status to "pending_approval".
        Claude MUST stop and wait for the user to say "approved" before continuing.
        """
        phase = phase or self._current_phase()
        phase_data = self._state["phases"].get(phase, {})

        # Check required validators
        validations = phase_data.get("validations", {})
        failed_validators = []
        missing_validators = []

        for v in REQUIRED_VALIDATORS:
            if v not in validations:
                missing_validators.append(v)
            elif not validations[v]["passed"]:
                failed_validators.append(v)

        if missing_validators:
            raise RuntimeError(
                f"[GateEnforcer] Cannot request approval for {phase}: "
                f"missing validations: {', '.join(missing_validators)}. "
                "Run all required validators before requesting approval."
            )

        if failed_validators:
            raise RuntimeError(
                f"[GateEnforcer] Cannot request approval for {phase}: "
                f"failed validators: {', '.join(failed_validators)}. "
                "Fix validation failures before requesting approval."
            )

        # Check cross-sections
        sections = phase_data.get("cross_sections", [])
        if len(sections) < MIN_CROSS_SECTIONS:
            raise RuntimeError(
                f"[GateEnforcer] Cannot request approval for {phase}: "
                f"only {len(sections)} cross-section(s) recorded "
                f"(minimum: {MIN_CROSS_SECTIONS}). "
                "Run render_cross_sections.py and record the outputs."
            )

        # All checks passed -- print gate message and update status
        self._state["phases"][phase]["status"] = "pending_approval"
        self._save()

        print()
        print("=" * 60)
        print(f"GATE: {phase.upper()} COMPLETE -- AWAITING APPROVAL")
        print("=" * 60)
        print(f"Validations passed : {', '.join(REQUIRED_VALIDATORS)}")
        print(f"Cross-sections     : {len(sections)} images")
        print()
        print("ACTION REQUIRED:")
        print("  1. Show the preview PNG to the user.")
        print(f"  2. Show all {len(sections)} cross-section images.")
        print("  3. Show validator output (PASS/WARN/FAIL lines).")
        print("  4. STOP. Do not write any more code or export files.")
        print("  5. Wait for the user to explicitly say 'approved'.")
        print("  6. Call gate.approve() only after explicit approval.")
        print("=" * 60)
        print()

    def approve(self, phase: str = None, approved_by: str = "user") -> None:
        """
        Mark a phase as approved. Must be called after request_approval().

        Args:
            phase:       Phase to approve. Defaults to pending_approval phase.
            approved_by: Who approved ("user" or a name).
        """
        phase = phase or self._pending_phase()
        phase_data = self._state["phases"].get(phase, {})

        if phase_data.get("status") != "pending_approval":
            raise RuntimeError(
                f"[GateEnforcer] Cannot approve {phase}: "
                f"status is '{phase_data.get('status', 'unknown')}', "
                "not 'pending_approval'. Call request_approval() first."
            )

        self._state["phases"][phase]["status"] = "approved"
        self._state["phases"][phase]["approved_by"] = approved_by
        self._state["phases"][phase]["approved_at"] = self._now()
        self._save()

        print(f"[Gate] {phase} APPROVED by {approved_by}.")

    def get_state(self) -> dict:
        """Return the full gate state dict (for debugging or logging)."""
        return self._state.copy()

    def is_approved(self, phase: str) -> bool:
        """Return True if the given phase has been approved."""
        return self._state["phases"].get(phase, {}).get("status") == "approved"

    # -- Internal helpers -----------------------------------------------------

    def _current_phase(self) -> str:
        """Return the most recently started in-progress phase."""
        in_progress = [
            p for p, data in self._state["phases"].items()
            if data.get("status") in ("in_progress", "pending_approval")
        ]
        if not in_progress:
            raise RuntimeError(
                "[GateEnforcer] No phase currently in progress. "
                "Call begin_phase() first."
            )
        return sorted(in_progress, key=self._phase_order_key)[-1]

    def _pending_phase(self) -> str:
        """Return the phase currently pending approval."""
        pending = [
            p for p, data in self._state["phases"].items()
            if data.get("status") == "pending_approval"
        ]
        if not pending:
            raise RuntimeError(
                "[GateEnforcer] No phase is pending approval. "
                "Call request_approval() first."
            )
        return sorted(pending, key=self._phase_order_key)[-1]


# -- CLI for inspection -------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Inspect or reset gate state for a part.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("gates_file", help="Path to a .gates.json file")
    parser.add_argument("--reset", metavar="PHASE",
                        help="Reset a phase back to in_progress (for recovery only)")
    args = parser.parse_args()

    gates_path = Path(os.path.realpath(args.gates_file))
    if not gates_path.exists():
        print(f"Error: file not found: {gates_path}", file=sys.stderr)
        sys.exit(2)

    with open(gates_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    if args.reset:
        phase = args.reset
        if phase not in state["phases"]:
            print(f"Error: phase '{phase}' not found in state", file=sys.stderr)
            sys.exit(2)
        state["phases"][phase]["status"] = "in_progress"
        with open(gates_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"Reset {phase} to in_progress.")
        return

    print(f"Part: {state.get('part_name', '(unknown)')}")
    print(f"State file: {gates_path}")
    print()
    for phase, data in state.get("phases", {}).items():
        status = data.get("status", "unknown")
        vals   = data.get("validations", {})
        secs   = data.get("cross_sections", [])
        approved_by = data.get("approved_by", "")
        print(f"  {phase}: [{status.upper()}]", end="")
        if approved_by:
            print(f" (approved by {approved_by})", end="")
        print()
        for v, result in vals.items():
            flag = "PASS" if result.get("passed") else "FAIL"
            print(f"    {v}: [{flag}]")
        print(f"    cross-sections: {len(secs)}")


if __name__ == "__main__":
    main()
