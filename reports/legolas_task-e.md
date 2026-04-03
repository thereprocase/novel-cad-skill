# Legolas Task E — Fix sub-phase skip in gate_enforcer.py

**Date:** 2026-04-02
**File:** `lib/gate_enforcer.py` lines 139-145
**Bug:** CONCERN 1 (MED)

## Problem

`_predecessor("phase_3")` returned `candidates[-1]` — the latest phase in the state dict with a sort key less than phase_3. If phase_2a was approved but phase_2b was never started (not in the state dict at all), `candidates[-1]` was phase_2a, which was approved. Result: phase_3 could begin, skipping phase_2b entirely.

## Fix

Replaced the "latest candidate" logic with an explicit check of ALL sub-phases of the prior major phase number:

1. Find all phases matching `phase_{N-1}[a-z]?` in the state dict
2. If none exist, fall back to `phase_{N-1}` directly
3. If sub-phases exist, iterate and return the first unapproved one — this blocks `begin_phase()` on the unapproved sub-phase
4. If all sub-phases are approved, return the last one (so `begin_phase()` sees it's approved and proceeds)

This means phase_3 cannot begin unless ALL of phase_2, phase_2a, phase_2b, etc. are approved.

## Limitation

If phase_2b was *planned* (by context_budget) but never *started* (never called `begin_phase("phase_2b")`), it won't be in the state dict, so this check won't catch it. The gate enforcer only knows about phases that have been started. A future improvement could cross-reference against the spec's `sub_phases` dict, but that requires the gate enforcer to read the spec — currently it doesn't.

## Files Changed

- `lib/gate_enforcer.py` lines 139-155: replaced `_predecessor()` non-sub-phase logic

## Verification

Test case: create gate enforcer, begin+approve phase_1, begin+approve phase_2a but NOT phase_2b, then try begin_phase("phase_3"). Should raise RuntimeError.
