# Frodo Session Notes — Radius Gauge v2

Date: 2026-04-06

## Decisions Made (as user proxy)

### Design Rules Established
1. **No outward bulge on back profile.** Back either follows measurement radius or chops inward. Never projects outward.
2. **Straight lines for non-gauging geometry.** Only the three arcs (convex, concave corner, edge notch) need precision curves. Everything else can be straight.
3. **Never project into workpiece space.** Body stays behind the gauging arcs so it doesn't interfere with the part being measured.
4. **Precision over leaf count.** Arc accuracy is sacred.
5. **Minimal surface area.** Scalpel, not paddle. No wasted flat expanses.
6. **Sturdy enough.** Won't snap when flexed into a corner, but not overbuilt.

### Architecture
- **Talon (medium/large):** Approved with straight back + rectangular hole boss. No arc, no bulge, no spline.
- **Dogbone (small):** Approved as-is from v1 architecture with G1 fixes.
- **Claw concept:** Rejected by user. Talon is the metaphor.

### Material Reduction Achieved
| Leaf | v1 (rect body) | v2 (straight back) | Reduction |
|------|----------------|--------------------|-----------|
| Medium R=25.4mm | 3486mm³ | 579mm³ | 83% |
| Large R=76.2mm | 22159mm³ | 5285mm³ | 76% |

## Issues Caught During Review
1. **Tip fillet silently swallowed errors** — fixed to fail loud with fallback
2. **String hole missing from talon renders** — hole wasn't visible, investigated and fixed
3. **Hole breaking through back edge on medium** — added rectangular boss
4. **Cross-section script broken** — trimesh 4.x tuple unpacking issue
5. **Back arc bulge** — fundamentally wrong approach, replaced with straight lines
6. **G1 kink at back-arc junction** — eliminated by removing back arc entirely

## What I Should Have Caught Sooner
- The back arc bulge was obvious wasted material from the first render. I approved the shape too quickly on first review — the user had to annotate a screenshot to show me. Need to be more critical on first pass, not just check if the shape "looks like a talon."

## Remaining Work
1. Batch PNG renderer needs Windows path fix
2. Manifold validator needs multi-body mode
3. Text orientation verification during slicer import
4. Test prints and fit testing
