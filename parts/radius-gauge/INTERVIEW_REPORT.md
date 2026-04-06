# Radius Gauge Set — Interview & Build Report

Date: 2026-04-05 through 2026-04-06

## What Was Asked For

A complete set of 3D-printable radius gauges covering 1/8" to 6" (SAE) and 3mm to 150mm (metric). Convex and concave profiles on each leaf. Printable on a Bambu P1S with multi-color MMU support.

The design interview ran 20 questions deep, covering use case, printer capabilities, size progressions, leaf architecture, labeling, material, organization, and tolerances. Two research agents ran in parallel during the interview — one on commercial gauge standards (Starrett, Mitutoyo, DIN 2275), one on existing 3D-printed gauge designs (Clough42, Blazek, kaje, RadGauge).

## What Was Built

**78 leaves across 6 rings** — 45 SAE (blue, white text) + 33 metric (red, white text). Each leaf is a multi-body STEP file with three named bodies: `leaf` (color), `text_top` (white), `text_bottom` (white). Debossed 0.5mm text inlays sit flush for layer-based MMU color change.

### Size Progressions

Logarithmic steps based on Weber's law (feelable difference). Gear shifts when relative step drops below threshold — 8% below 1.5", tighter 6% above 1.5".

| Ring | SAE | Metric |
|------|-----|--------|
| Small | 13 leaves: 1/8"–1/2" by 1/32" | 14 leaves: 3–13mm (0.5mm then 1mm) |
| Medium | 19 leaves: 9/16"–2-1/8" (1/16" then 1/8") | 11 leaves: 14–50mm (2mm then 5mm) |
| Large | 13 leaves: 2-1/4"–6" (1/4" then 1/2") | 8 leaves: 60–150mm (designer favorites) |

Key additions by user request: 13mm, 15mm (common design callouts), 120mm (circular geometry). No decimal-mm sizes that only exist as SAE conversions.

### Three Gauging Profiles Per Leaf

1. **Convex** — measures concave (inside) features. 120/90/60 degree sweep by ring size.
2. **80-degree concave corner** — measures convex fillets in 90-degree corners. 5-degree wall clearance per side.
3. **40-degree concave edge notch** — shallow sweep for measuring radii along an edge.

### Two Leaf Architectures

**Small (R ≤ 12.7mm): Dual-ended dogbone.** Convex arc on one end, concave scoop biting into the other end, edge notch on the top edge. Body width derived from convex arc geometry.

**Medium/Large (R > 12.7mm): Talon.** Convex and concave arcs share a tip point, like a raptor's talon. Tight jaw angle (110° medium, 90° large). No rectangular body — smooth back arc connects the tangent departures. 72–82% volume reduction over the original rectangular-body design.

### Labeling

- SAE: fractions always ("1/4", "1-1/8", "2-1/4"), decimal on reverse when space permits
- Metric: decimal mm with unit suffix ("25mm", "3.5mm")
- Sans-serif bold, 4mm minimum / 6mm preferred, driven by available area
- Double-sided: primary on top, secondary on bottom

## How We Got Here

### Phase 0: Requirements (20 questions)

Established use case (hobby projects, measuring other 3D prints), printer (P1S, 0.3–0.8mm nozzles, calibrated), material (PLA default), organization (6 rings on strings), color strategy (blue SAE / red metric / white text), and labeling (fractions always, debossed multi-body). Two research agents reported on commercial standards and existing 3D designs.

### Phase 1: Base Shapes (15 commits, 4 major redesigns)

The geometry went through significant iteration:

1. **Dual-ended for all sizes** — convex on one end, concave on the other. Worked for small radii. Medium/large leaves were 272mm tall and shaped like arrowheads.

2. **Talon introduced for medium/large** — convex and concave arcs share a tip. Dramatic size reduction (medium: 97mm to 37mm height). Small stayed dual-ended.

3. **Arc-to-body transition crisis** — every version had angular kinks where curved arcs met straight body sides. The convex end "dead-ended into a straight line." Multiple fix attempts (tangent body sides, wider body, narrower body, 180-degree sweep) failed to resolve the fundamental G0-but-not-G1 discontinuity.

4. **War council deployed** — Sauron (penetrating analysis) and Gandalf (architecture review) reviewed the design:
   - Gandalf: "Kill dual-ended. Talon everywhere. The tangent problem doesn't exist on a talon."
   - Sauron: "All transitions lack G1 continuity. Body lines must depart along arc tangent direction. Dual-ended is correct for small but needs tangent-continuous sides."

5. **G1 rewrite** — complete rewrite of both architectures. Body lines depart from arcs along their tangent direction. Dual-ended small leaf fixed with explicit prong geometry at concave end.

6. **Sauron+Frodo iteration loops** — code+review cycles to fix edge notch direction (RadiusArc sign), cat ears on concave end (removed prong artifacts), and dimension bugs (8x radius multiplier, rotated talon orientation).

7. **Talon redesign** — user pushed for tighter jaw and no rectangular body. Jaw angles tightened from 160/140 to 110/90 degrees. Rectangular spine replaced with smooth back arc. 72–82% material reduction.

### Phase 2: Text Labels (2 commits)

Multi-body debossed text using build123d's `Text` class. Fraction formatting with `fractions.Fraction` handles mixed numbers ("2-1/4"). Text placement auto-avoids string hole. Talon text area computed from arc geometry.

### Phase 3: Batch Generation (3 commits)

`generate_all.py` produces all 78 STEP + PNG files. Build-plate validation confirms largest leaf (R=152.4mm) at 235x199mm fits P1S. Color metadata (blue/red/white) embedded via `build123d.Color`.

## Compliance

Frodo's final review: **97% spec compliance.**

| Requirement | Status |
|---|---|
| 78 leaves, correct progressions | Done |
| Three profiles per leaf | Done |
| Dual-ended small / talon medium+large | Done |
| Multi-body STEP (leaf + text_top + text_bottom) | Done |
| Debossed 0.5mm text, flush inlay | Done |
| Fractions, mixed numbers, metric labels | Done |
| Double-sided labels | Done |
| Color metadata (blue/red/white) | Done |
| Build-plate validation | Done — all fit |
| String hole offset | Done — 35% from concave end |
| No shrinkage compensation | Done |
| Separate step/ and png/ output folders | Done |

Remaining 3%: secondary decimal labels fall back to primary-on-both-faces on small leaves (correct per spec: "when space permits").

## Output

```
parts/radius-gauge/
  output/
    step/   — 78 multi-body STEP files
    png/    — 78 preview renders
  phase1_leaf_body.py    — leaf body generator (dual-ended + talon)
  phase2_text.py         — text label module
  generate_all.py        — batch generation script
  radius_gauge.spec.json — machine-readable spec
  phase0_notes.md        — interview requirements
  research/              — industry + 3D print design research
```

## Minimum Material Analysis

For the large talon (R=76.2mm), the theoretical minimum 2D profile area is 1,475 mm² (3,688 mm³ volume). The current design is 6,231 mm³ — 1.7x the theoretical minimum. The bottleneck is the structural bridge between arc endpoints (172mm span, 515 mm² of connecting material). Further optimization would require thinner bridges or tighter jaw angles.

## What Would Come Next

1. **Slicer validation** — import multi-body STEPs into BambuStudio, verify color assignment workflow
2. **Test prints** — small ring first, check arc accuracy against commercial gauge or known-radius objects
3. **Fit testing** — verify concave 80-degree profile seats in 90-degree corners, verify edge notch is usable
4. **Iterate** — adjust parameters based on physical testing (handle feel, text readability, arc accuracy)
