# Existing 3D-Printed Radius Gauge Designs

Research conducted 2026-04-05. Source: Printables, GitHub, MakerWorld, Hackaday.

## Notable Designs

### Clough42 — Imperial and Metric Card Gauges
- **Source:** Printables #202233
- **Type:** Card-style (not fan). Each card has 5 measuring edges: 90-degree convex, 180-degree convex, 45-degree concave, 90-degree concave, 180-degree concave.
- **Range:** Imperial 1/32"-1" by 1/32" (32 cards). Metric 1-25mm by 0.5mm.
- **Engine:** Fully parametric OpenSCAD with batch generation scripts.
- **Key insight:** Printing gauges on the same printer you'll measure creates a closed-loop calibration. The gauge automatically knows what "R 1/4" means on your machine.
- **Print settings:** 0.2mm layers, 40% infill, no supports. eSun PETG recommended.

### Michal Blazek — Fan-style 1-20mm
- **Source:** Printables #137696
- **Stats:** 601 reviews, 4.91/5 stars — most popular design.
- **Type:** Traditional fan with bolt pivot. Requires 2x M5x30 + M5 lock nuts.
- **Material:** Prusament PETG, no supports, 0.15mm layer height.
- Both convex and concave on each leaf.

### kaje — Large Radius Gauges, Inch
- **Source:** Printables #44577
- **Range:** 11 gauges spanning 2"-48".
- **Type:** Individual cards (not fan). Includes storage box.
- **Settings:** PLA, 100% infill, concentric top/bottom, 0.2mm layers.
- Positioned as "a starting point for test fit," not precision measurement.

### mikepilat — Parametric OpenSCAD
- **Source:** GitHub mikepilat/3d_print_radius_gauge
- **Type:** Cross/plus-shaped leaf. Convex semicircle on one arm, concave on opposite.
- **Params:** 25mm wide, 50mm long arms, 3mm thick, 1mm emboss depth.
- **Text:** Bold Helvetica, size 8, embossed via linear_extrude.
- No pivot hole — standalone cards.

### VC Design — Convex/Concave 1-30mm
- **Source:** Printables #1055124
- **Stats:** 4.67/5, 2053 saves.
- **Type:** Separate leaves for convex and concave — 32 files each (64 total).
- Fan-style assembly.

### RadGauge (Fredrik Welander) — Sliding-Arm Mechanism
- **Source:** MakerWorld series (Nano, standard, Giga, X, Dual)
- **Type:** Single instrument — sliding arm converts linear displacement to angular readout via gears.
- **Accuracy:** RadGauge-X +/-0.1mm. Original +/-0.3mm. GIGA tested at +/-0.01" (~0.25mm).
- Requires very tight print tolerances (0.1mm gear clearance).
- Different approach entirely — not a gauge set.

### Hackaday Caliper Attachment
- **Source:** Hackaday (2018)
- **Type:** Jig clips onto digital calipers. Formula: radius = distance * 2.414.
- Good for quick checks, not a replacement for gauge set.

## Accuracy Achievable

| Method | Tolerance | Notes |
|---|---|---|
| FDM (0.2mm layers) | +/-0.2-0.5mm | Well-calibrated, flat features |
| FDM (same printer) | Effectively perfect | Closed-loop: gauge matches parts |
| SLA/Resin | +/-0.05-0.15mm | No staircase on XY arcs |
| SLS | +/-0.3mm floor | Grainy surface |

## Design Approaches

**Card/Individual (Clough42, mikepilat, kaje):**
- No assembly, printable flat, easy to store in box
- Cons: easy to lose individual cards

**Fan-Style (Blazek, VC Design):**
- All sizes in one tool, familiar form factor
- Requires hardware (M3/M5 bolt), pivot adds stress point

**Five-Edge Card (Clough42, commercial PEC):**
- Most information-dense — 5 profiles per card
- Mirrors commercial design (PEC explicitly lists "5 measuring surfaces")
- Best model for parametric generation

## Material Recommendations

| Material | Shrinkage | Warping | Wear | Verdict |
|---|---|---|---|---|
| PLA | 0.3% | Very low | Low (brittle) | Best dimensional accuracy |
| PETG | 0.3-0.8% | Low | Good | Best for shop tools |
| ABS | 0.7-0.8% | High | Good | Not recommended |
| Resin | Varies | N/A | Moderate | Best for small radii |

PETG showed increased hardness after weathering — nice property for shop tools.

## Print Orientation

**Flat on bed is correct.** Critical measuring edges are perimeter walls — highest-resolution FDM feature. If printed on edge, staircase effect on measuring surface.

Best settings:
- 0.15mm layer height (diminishing returns below)
- 100% infill or concentric top/bottom
- Slow perimeter speed (30-40mm/s)
- 2-3 perimeter walls minimum

## Large Radius Challenges (3"+)

- Partial arc (45-90 degrees) instead of full semicircle
- Reduced arc + extended handle
- Abandon fan for large sizes — individual cards in box
- Transition points: ~1" and ~3"

## Labeling

- **Debossed preferred** over embossed — more durable, prints cleaner
- Minimum depth: 0.3mm (readable), 0.5-0.6mm (recommended)
- Font: sans-serif bold, minimum 3mm debossed / 4mm embossed
- Recommended: 5-6mm character height
- Nozzle rule: min feature width = nozzle diameter x 2.5 (1.0mm at 0.4mm nozzle)
- Multi-material: debossed at 0.5mm depth filled with contrasting filament
