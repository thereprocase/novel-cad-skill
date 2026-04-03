# Smoke Test Findings — Pen Organizer (2026-04-03)

First end-to-end test of novel-cad-skill via trio channel.
Full test log: `pen-organizer/TEST_LOG.md`
Agent build log: `pen-organizer/BUILD_LOG.md`

---

## SKILL.md / BUILD123D_REFERENCE.md improvements

### 1. Chamfer warning for union bodies
- **What:** Chamfering a union of two boxes fails when the intersection creates short edges (< chamfer radius)
- **Where it failed:** Phase 1 attempt 1 — `ValueError: Failed creating a chamfer`
- **Fix:** Add warning to SKILL.md: "For stepped/L-shaped bodies, prefer single-profile extrusion over box union. Union creates short internal edges that break chamfer operations."

### 2. Algebra-mode boolean subtraction with rotated cutters
- **What:** Algebra-mode `Part - cutter` doesn't clip the cutter to the target body's extent. A rotated box cutter extending below Z=0 produces a result taller than expected.
- **Where it failed:** Phase 2 attempt 1 — bounding box 112mm instead of 80mm
- **Fix:** Add warning to BUILD123D_REFERENCE.md: "Always use in-context operations (BuildPart + tilted workplane) for angled cuts. Algebra-mode subtraction preserves the full extent of the cutter."

### 3. Phase 3 scope for simple parts
- **Observation:** Phase 3 (validation + export) made zero geometry changes. For simple parts this is a no-op phase.
- **Suggestion:** Consider allowing Phase 2 → final delivery for parts with no print optimization needs. Keep Phase 3 for complex parts requiring support blockers, seam hints, etc.

---

## Rendering pipeline issues

### 4. Cross-section cut face vs solid face visual distinction
- **Severity:** Medium — UX clarity
- **What:** Cut faces and far-away solid faces use nearly identical visual styles. Hard to tell "knife cut through material" from "solid face viewed from distance."
- **Frodo UX report:** `pen-organizer/TODO_cross_section_ux.md` (pending)

### 5. Axis label mapping on XZ plane sections
- **What:** Side profile cross-section (XZ plane) shows "200.00mm" annotation on the 80mm dimension
- **Where:** `render_cross_sections.py`
- **Agent noted this in BUILD_LOG.md** — confirms the skill's self-review caught it but couldn't fix inline

---

## Validation pipeline (working well)

- `validate_geometry` caught the 112mm bounding box error immediately in Phase 2
- Gate checkpoint system enforced correctly — agent waited for human approval at each phase
- Manifold verification clean at every phase
- Agent self-documented all improvement items in its own BUILD_LOG — good practice

---

## Overall assessment

The novel-cad-skill pipeline works. The validation catches real errors, the gate system enforces review checkpoints, and the agent self-corrects on failures. Main improvements needed are in the reference docs (prevent known gotchas) and the rendering pipeline (visual clarity).
