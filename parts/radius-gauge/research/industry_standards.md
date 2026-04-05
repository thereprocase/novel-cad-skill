# Industry Standards Research — Radius Gauges

Research conducted 2026-04-05. Source: commercial specifications, manufacturing standards, metrology references.

## 1. Standard Radius Sets

### Metric Sets

**Small set (15-17 leaves):** 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10, 11, 12 mm — half-millimeter steps up to 6, then full millimeter steps.

**Large set (32-34 leaves):** Extends to 25 mm, adding 13, 14, 15, 16, 17, 18, 19, 20, 22, 25 mm.

Most metric sets include both convex and concave profiles on each leaf (one on each end).

### Imperial Sets

**Common small set (16 leaves):** 1/32, 1/16, 3/32, 1/8, 5/32, 3/16, 7/32, 1/4, 5/16, 3/8, 7/16, 1/2, 9/16, 5/8, 3/4, 1 inch.

1/32" increments up to 1/4", then 1/16" to 1/2", then 1/8" to 1". Roughly logarithmic — finer resolution at the small end.

### Major Brands

- **Starrett** — S167 series. S167C is the classic 25-leaf set (1/32" to 1/2"). S167Z (metric). Prestige brand in North American shops.
- **Mitutoyo** — 186-series. 186-101 through 186-106. Japanese manufacturing, tight tolerances.
- **SPI (Swiss Precision Instruments)** — Mid-range professional. Mirrors Starrett progressions.
- **General Tools** — Budget-friendly. Adequate for woodworking and general use.
- **Fowler** — Professional-grade, common in QC. 52-480 series covers metric and imperial.
- **iGaging** — Budget import, surprisingly decent.

### Progression Logic

Percentage resolution matters more than absolute. Step size grows with nominal size. Each gear shift happens roughly at a doubling of the base radius.

## 2. Physical Design

### Leaf Thickness

Stamped from spring-tempered steel. Typical: **0.6-0.8 mm** (Starrett ~0.7 mm). Balance between fitting tight spots and rigidity.

For 3D printing: 1.5-2.5 mm for rigidity. The gauging edge is what matters, not body thickness.

### Leaf Profile

**Arc length:** 90-120 degrees (NOT a full semicircle). Full 180 degrees would prevent fitting into inside corners.

**Convex leaves:** Bullet-nose shape — arc blends tangentially into straight leaf sides.

**Concave leaves:** U-shaped notch with arc at bottom, straight sides tangent to arc at each end.

**Dual-ended:** Most commercial sets put convex on one end, concave on the other. Standard Starrett/Mitutoyo approach.

### Handle/Tab Design

- Pivot hole near center, 4-5 mm diameter
- Size marking near pivot
- Total length: 60-80 mm (small), 80-120 mm (medium), scales up for large
- Leaf width: 10-15 mm typical

### Organization

- **Fan pivot (most common):** Shared pivot screw/rivet with knurled nut
- **Individual leaves in case:** For large-radius or high-precision sets
- **Ring sets:** Less common for radius gauges

## 3. Tolerances

- **Workshop grade:** +/-0.05 mm (+/-0.002"). Most affordable sets.
- **Inspection grade:** +/-0.02 mm (+/-0.001"). Starrett, Mitutoyo inspection-grade.
- **Reference/calibration grade:** +/-0.005 mm (+/-0.0002"). Expensive individual gauges.

Standards: **DIN 2275** (radius gauges), **JIS B 7524** (Japanese).

Light-gap discrimination by experienced machinists: ~0.01 mm — finer than gauge tolerance itself.

## 4. Material Considerations for 3D Printing

### FDM

- Print flat on bed (arc in XY plane) — edge quality depends on XY resolution (~0.1-0.2 mm for 0.4 mm nozzle)
- Layer height: 0.1 mm minimum, 0.05 mm if printer handles it
- Achievable accuracy: +/-0.1 mm without post-processing, +/-0.05 mm with sanding
- PLA: rigid, dimensionally stable, low shrinkage — best for gauges
- PETG: slightly more flexible but better shop durability
- ABS: poor choice (shrinkage, warping)

### Critical Print Parameters

- Perimeters: 4-5 (perimeters define the edge)
- Infill: 100% for thin leaves
- Speed: 30-40 mm/s outer perimeter
- Cooling: maximum
- First layer: perfect (elephant foot distorts gauge edge)
- No brim touching gauging edge

### SLA/Resin

- XY resolution: 0.035-0.050 mm
- Achievable accuracy: +/-0.05 mm without post-processing
- Downsides: brittle, UV-degradable, 2-3 mm thickness needed

### Minimum Feature Sizes

- Smallest useful FDM gauge radius: ~3 mm (1/8")
- Gauge marking text: minimum ~4 mm tall for FDM
- Leaf thickness: 1.5 mm minimum for FDM

## 5. Use Cases and Accuracy Requirements

| Application | Typical Accuracy | FDM Suitable? |
|---|---|---|
| Machining (production) | +/-0.05 mm | Marginal |
| Machining (aerospace) | +/-0.01 mm | No |
| Welding inspection | +/-0.5 mm | Excellent |
| Woodworking | +/-0.25 mm | Good |
| Sheet metal / fabrication | +/-0.1-0.25 mm | Good |
| Automotive / motorsport | Varies | Good for large radii |
| QC / inspection | Matches drawing tolerance | Depends |

## 6. Large Radius Gauges (3-6")

### The Commercial Gap

Most sets stop at 1" (25 mm). Beyond that:
- Starrett: no standard sets above 1/2"
- Mitutoyo: largest standard set goes to 25 mm
- Specialty suppliers: $20-50+ per leaf, often made to order

### How Shops Handle Large Radii

1. CNC/laser-cut templates from sheet steel or aluminum (most common)
2. Printed templates on card stock (rough checking, 2"+)
3. Spherometers, CMMs, optical comparators (precision work)
4. Adjustable radius gauges (pins + dial indicator)

### Design Differences

- **Reduced arc angle:** 30-60 degrees (vs 90-120 for small)
- **Chord-based design:** Curved notch/end with much less than full diameter
- **Stiffness critical:** Thicker stock or structural ribbing
- **Separate convex/concave:** Dual-ended becomes unwieldy

Suggested arc lengths for 3D-printed set:
- 1/8"-1/2": 120 degrees
- 1/2"-2": 90 degrees
- 2"-4": 60 degrees
- 4"-6": 45 degrees (chord length ~4.6" at 6" radius)

Fan pivot impractical above ~2" radius — use individual leaves or sub-sets.

## 7. Markings and Labeling

### Commercial Method

Chemically etched and paint-filled:
1. Resist applied with text pattern
2. Acid etches ~0.05-0.1 mm deep
3. Paint wiped into depression
4. Excess wiped off

### What's Marked

- "R" prefix + nominal value
- Units (mm or inch symbol)
- Some mark both radius and diameter
- Brand mark on at least one leaf

### For 3D Printing

Recommended: **Debossed text, 0.4-0.5 mm deep**, designed for paint fill or multi-color MMU. Sans-serif font at 4-5 mm height minimum.
