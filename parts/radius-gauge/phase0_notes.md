# Radius Gauge Set — Phase 0 Requirements

> **Spec file:** [radius_gauge.spec.json](./radius_gauge.spec.json)
> **Research:** [research/industry_standards.md](./research/industry_standards.md) | [research/existing_3d_designs.md](./research/existing_3d_designs.md)

## Overview
Dual-system (SAE + metric) radius gauge set. Three profiles per leaf: convex, 80-degree concave corner, 40-degree concave edge notch. Three rings per system, six rings total. Printed on Bambu P1S.

## Systems & Colors
- **SAE:** Blue leaves, white text. Range 1/8" to 6".
- **Metric:** Red leaves, white text. Range 3mm to 150mm.
- Each system uses its own natural progression — no cross-system equivalents.
- No decimal mm just to hit an SAE fraction.

## Progression Philosophy
Logarithmic steps based on feelable difference (Weber's law). Finer increments at small radii, coarser at large. Gear shifts when relative step drops below threshold.
- **Below 1.5" / 38mm:** shift at ~8% relative
- **Above 1.5" / 38mm:** tighter threshold, shift at ~6% relative
- Hit all major fractions and designer-standard round numbers at each scale

### SAE Progression (APPROVED)

**Small Ring (1/32" steps) — 13 leaves:**
1/8, 5/32, 3/16, 7/32, 1/4, 9/32, 5/16, 11/32, 3/8, 13/32, 7/16, 15/32, 1/2

**Medium Ring (1/16" to 1-1/4", then 1/8" to 2-1/8") — 19 leaves:**
9/16, 5/8, 11/16, 3/4, 13/16, 7/8, 15/16, 1, 1-1/16, 1-1/8, 1-3/16, 1-1/4, 1-3/8, 1-1/2, 1-5/8, 1-3/4, 1-7/8, 2, 2-1/8

**Large Ring (1/4" to 4-1/4", then 1/2" to 6") — 13 leaves:**
2-1/4, 2-1/2, 2-3/4, 3, 3-1/4, 3-1/2, 3-3/4, 4, 4-1/4, 4-1/2, 5, 5-1/2, 6

**Total SAE: 45 leaves.** All major fractions (1/4" and up) present. Clean handoffs between rings.

### Metric Progression (APPROVED)

**Small Ring (0.5mm to 6, then 1mm to 13) — 14 leaves:**
3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10, 11, 12, 13

**Medium Ring (2mm steps to 18 with 15 added, designer 5s from 20) — 11 leaves:**
14, 15, 16, 18, 20, 25, 30, 35, 40, 45, 50

**Large Ring (designer favorites) — 8 leaves:**
60, 75, 80, 90, 100, 120, 125, 150

**Total Metric: 33 leaves.** 13 and 15 added as common design callouts. 120 added for circular geometry.

### Grand Total: 78 leaves across 6 rings (45 SAE + 33 metric)

## Three Profiles Per Leaf
- **End A — Convex:** Measures concave (inside) features. 120/90/60 degree sweep by ring size.
- **End B — Concave Corner (80 degrees):** Measures convex fillets in 90-degree corners. 5-degree wall clearance per side so gauge arms clear workpiece walls.
- **Side — Concave Edge (40 degrees):** Shallow-sweep concave notch for measuring convex radii along an edge where full concave can't straddle. Placed as side notch on leaf body.

## Leaf Architecture by Ring

| Ring | Architecture | Thickness | Convex Sweep | Jaw Angle | String Hole | Relief Fillet |
|------|-------------|-----------|-------------|-----------|-------------|---------------|
| Small | Dual-ended | 2.0mm | 120 deg | N/A | 4mm | 0.8mm |
| Medium | Talon | 2.2mm | 90 deg | 160 deg | 5mm | 1.0mm |
| Large | Talon | 2.5mm | 60 deg | 140 deg | 6mm | 1.2mm |

**Small (dual-ended):** Convex on one end, concave on the other, 40-deg edge notch on side.
**Medium/Large (talon):** Convex and concave arcs share a tip, meeting at a point like a claw. Tighter jaw angle at large sizes for material efficiency. 40-deg edge notch on the back spine. String hole in body meat between the arcs.

Concave corner sweep: 80 degrees all sizes. Concave edge sweep: 40 degrees all sizes.

## Multi-Body Color Strategy
- Three bodies per leaf: `leaf` (blue/red), `text_top` (white), `text_bottom` (white)
- Debossed 0.5mm, text inlays flush with surface
- All top surfaces flat for clean MMU layer-based color change
- Clever body names for slicer identification

## Labeling
- **SAE Primary:** Fraction always (stacked where area allows, inline where tight)
- **SAE Secondary:** Decimal inches when space permits
- **Metric Primary:** Decimal mm with unit suffix
- **Double-sided:** Fraction on one face, decimal on other when both won't fit one side
- **Font:** Sans-serif bold, min 4mm height, preferred 6mm
- **Size driven by available area** — must fit on gauge, never overflow
- **Clean** — no branding, no logo, no version

## Dimensional Tolerance
- Models are dead-nuts nominal +/-0.01mm
- No shrinkage compensation — printer calibration is the printer's problem
- Same-printer closed-loop cancels systematic error (see [research/existing_3d_designs.md](./research/existing_3d_designs.md) — Clough42 insight)

## Printer Defaults
- **Printer:** Bambu P1S
- **Nozzle:** 0.4mm default (0.3mm noted as upgrade for small radii)
- **Material:** PLA default (PETG/ASA available and calibrated)
- **Layer height:** 0.12mm
- **Infill:** 100%
- **Perimeters:** 4+
- **Print orientation:** Flat on bed

## Organization
- 3 rings per system, string through offset hole
- Smallest to largest on each ring
- String hole offset toward concave-corner end (leaves hang with convex up)
- No case, no hardware beyond string

## Script Architecture
- Single parametric build123d script preferred
- May split to one script per size category if complexity demands
- Parameter table drives all leaf generation
- See [../../SKILL.md](../../SKILL.md) for build123d workflow and validation pipeline
