# Sauron's Review: Radius Gauge Leaf Body Generator

Date: 2026-04-05

## Critical Findings

### BUG 1-3: All arc-to-body transitions lack G1 continuity

Every arc-to-straight transition in the codebase is G0 (position-continuous) but NOT G1 (tangent-continuous). The code draws straight body lines to arc endpoints without matching tangent direction.

- Medium talon convex-to-body: **80-degree kink**
- Small leaf convex-to-body: **30-degree kink**
- All talon concave-to-body: **60-70 degree kinks**

**Root cause:** Body lines depart from arc endpoints in cardinal directions (horizontal/vertical) rather than along the arc's tangent at that point.

**Fix:** At every arc endpoint, compute the tangent direction and draw the body line departing in that direction. The body becomes non-rectangular — wider at the measuring end, tapering toward the handle.

### BUG 4: Small leaf concave end has flat stubs blocking seating

The concave corner arc endpoints are at x=+-4.08mm, but the body extends to x=+-5.50mm. The 1.42mm flat stubs on each side prevent the concave profile from seating into a 90-degree corner. Commercial gauges solve this by having the concave end protrude from the body.

## Major Findings

### BUG 5: Edge notch position unvalidated against labeling
### BUG 6: Talon spine notch sagitta too shallow at large radii (~1.5mm for medium)
### BUG 7: Fillet error handling silently swallows failures

## Minor Findings

### BUG 8: Body width over-constrained to convex sweep
### BUG 9: String hole position uses magic constant (0.35)

## The Fundamental Fix

**Current:** Calculate intersection, draw straight lines to it. Arc and sides share a point but disagree on direction.

**Correct:** Body sides are lines tangent to the arc at the departure point. Arc and side share both point AND direction (G1 continuity).

For the talon: the body top/bottom lines depart from the arc endpoints along the tangent direction, then transition to horizontal/vertical to form the spine region.

## On Architecture

Sauron disagrees with Gandalf: dual-ended is correct for small gauges (talon too small/fragile at R=6.35mm). But the dual-ended body needs tangent-continuous sides at both ends — the body tapers from the arc width, like a commercial gauge leaf.

The G1 fix is the same regardless of architecture. It applies to dual-ended and talon equally.
