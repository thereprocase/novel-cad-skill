# build123d API Quick Reference

## Mode Selection

| Mode | When to use | Scoping |
|------|------------|---------|
| **Builder** | Parts with >3 features, enclosures, trays | `with BuildPart/BuildSketch/BuildLine` context managers |
| **Algebra** | Simple parts, quick booleans, <3 operations | Stateless expressions, operator overloading |

**Never mix modes in the same part.** Pick one and commit.

---

## Builder Mode Patterns

### Basic box with shell
```python
from build123d import *

with BuildPart() as part:
    Box(width, depth, height)
    Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)
    Shell(*part.faces().sort_by(Axis.Z).last, thickness=-wall)

result = part.part
export_step(result, "box.step")
```

### Sketch + extrude
```python
with BuildPart() as part:
    with BuildSketch() as sk:
        Rectangle(width, depth)
        # or: Circle(radius)
        # or: RectangleRounded(width, depth, radius)
    Extrude(amount=height)
```

### Nested sketch for holes
```python
with BuildPart() as part:
    Box(width, depth, height)
    with BuildSketch(part.faces().sort_by(Axis.Z).last):
        with Locations([(x1, y1), (x2, y2)]):
            Circle(hole_r, mode=Mode.SUBTRACT)
    Extrude(amount=-depth, mode=Mode.SUBTRACT)
```

### Hole and CounterBoreHole (inside BuildPart)
```python
with BuildPart() as part:
    Box(50, 50, 10)
    with Locations([(10, 10), (-10, -10)]):
        Hole(radius=2.15)                    # M4 through-hole
    with Locations([(10, -10)]):
        CounterBoreHole(radius=2.15, counter_bore_radius=4.5,
                        counter_bore_depth=3.0)
```

### BuildLine for complex profiles
```python
with BuildPart() as part:
    with BuildSketch() as sk:
        with BuildLine() as ln:
            l1 = Line((0, 0), (10, 0))
            l2 = Line(l1 @ 1, (10, 20))     # @ 1 = end point
            l3 = Line(l2 @ 1, (0, 20))
            Line(l3 @ 1, l1 @ 0)             # close the loop
        MakeFace()
    Extrude(amount=5)
```

---

## Algebra Mode Patterns

### Boolean operations
```python
from build123d import *

box = Box(50, 30, 10)
pocket = Pos(5, 0, 2) * Box(20, 15, 8)     # position then shape
result = box - pocket                        # subtract
result = box + rib                           # union
result = box & slab                          # intersect
```

### Transforms
```python
Pos(x, y, z)              # translate
Rot(rx, ry, rz)            # rotate (degrees, around X, Y, Z)
Loc(pos, rot)              # combined location
Pos(10, 0, 5) * Rot(0, 0, 45) * Box(10, 10, 5)  # chain transforms
```

### Fillet/chamfer in algebra mode
```python
box = Box(50, 30, 10)
box = fillet(box.edges().filter_by(Axis.Z), radius=3)
box = chamfer(box.edges().filter_by(Axis.Z).sort_by(Axis.Z).first, length=0.5)
```

---

## Selectors

Selectors return `ShapeList` objects. Chain methods to narrow the selection.

### Face selectors
```python
part.faces()                                # all faces
part.faces().sort_by(Axis.Z)               # sorted low-to-high along Z
part.faces().sort_by(Axis.Z).last          # top face (+Z)
part.faces().sort_by(Axis.Z).first         # bottom face (-Z)
part.faces().sort_by(Axis.X).last          # rightmost face (+X)
part.faces().filter_by(GeomType.PLANE)     # only planar faces
part.faces().filter_by(Axis.Z)             # faces with normal along Z
part.faces() > Axis.Z                      # faces with normal in +Z direction
part.faces() < Axis.Z                      # faces with normal in -Z direction
```

### Edge selectors
```python
part.edges()                                # all edges
part.edges().filter_by(Axis.Z)             # edges parallel to Z
part.edges().filter_by(GeomType.CIRCLE)    # circular edges
part.edges().sort_by(Axis.Z).first         # lowest edges
part.edges().group_by(Axis.Z)              # group by Z position
part.edges().group_by(Axis.Z)[-1]          # top group of edges
```

### Vertex selectors
```python
part.vertices()                             # all vertices
part.vertices().sort_by(Axis.Z).last       # highest vertex
```

### CadQuery selector migration

| CadQuery | build123d |
|----------|-----------|
| `.faces(">Z")` | `.faces().sort_by(Axis.Z).last` |
| `.faces("<Z")` | `.faces().sort_by(Axis.Z).first` |
| `.faces("+Z")` | `.faces().filter_by(Axis.Z)` |
| `.edges("\|Z")` | `.edges().filter_by(Axis.Z)` |
| `.edges(">Z")` | `.edges().sort_by(Axis.Z).last` |

---

## Common Operations

### Extrude
```python
Extrude(amount=10)                          # along sketch normal
Extrude(amount=10, both=True)               # symmetric extrude
Extrude(amount=-5, mode=Mode.SUBTRACT)      # cut into existing part
```

### Revolve
```python
with BuildPart() as part:
    with BuildSketch(Plane.XZ) as sk:
        # draw half-profile
        with BuildLine():
            Line((0, 0), (10, 0))
            Line((10, 0), (10, 20))
            Line((10, 20), (0, 20))
            Line((0, 20), (0, 0))
        MakeFace()
    Revolve(axis=Axis.Z)
```

### Loft
```python
with BuildPart() as part:
    with BuildSketch(Plane.XY) as bottom:
        Rectangle(20, 20)
    with BuildSketch(Plane.XY.offset(30)) as top:
        Circle(10)
    Loft()
```

### Shell
```python
Shell(*part.faces().sort_by(Axis.Z).last, thickness=-wall)
# Negative thickness = shell inward (usual for enclosures)
# Can remove multiple faces: Shell(top_face, bottom_face, thickness=-wall)
```

### Fillet and Chamfer
```python
Fillet(*part.edges().filter_by(Axis.Z), radius=3)
Chamfer(*part.edges().sort_by(Axis.Z).first, length=0.5)
# Note: unpack edge lists with * — these take individual edges, not a list
```

### Mirror
```python
Mirror(*part.faces().sort_by(Axis.X).last, about=Plane.YZ)
```

### Text (deboss)
```python
with BuildPart() as part:
    Box(50, 20, 5)
    with BuildSketch(part.faces().sort_by(Axis.Z).last):
        Text("LABEL", font_size=8, align=(Align.CENTER, Align.CENTER))
    Extrude(amount=-0.8, mode=Mode.SUBTRACT)
```

---

## Export Functions

```python
from build123d import export_step, export_stl

export_step(result, "part.step")
export_stl(result, "part.stl")

# These are module-level functions, NOT methods on the part object.
# Wrong: result.export_step("part.step")
# Right: export_step(result, "part.step")
```

---

## Gotchas and Known Traps

### 1. Extrude direction
`Extrude` direction defaults to the sketch normal, not always +Z. After the first extrude, verify with bounding box:
```python
bb = part.part.bounding_box()
print(f"Bounds: X={bb.min.X:.1f}..{bb.max.X:.1f}, "
      f"Y={bb.min.Y:.1f}..{bb.max.Y:.1f}, "
      f"Z={bb.min.Z:.1f}..{bb.max.Z:.1f}")
```

### 2. Fillet/Chamfer take unpacked edges
```python
# Wrong:
Fillet(part.edges().filter_by(Axis.Z), radius=3)
# Right:
Fillet(*part.edges().filter_by(Axis.Z), radius=3)
```

### 3. Mode.SUBTRACT is immediate
Inside a `BuildPart` context, `Mode.SUBTRACT` applies immediately — not lazily like CadQuery's `.cut()`. The geometry changes in-place within the context.

### 4. Shell before fillet on the same edges
Same OCCT kernel = same ordering constraint. If you shell and fillet edges that share faces, shell first, then fillet the resulting edges. Reversing the order causes topology errors.

### 5. Revolve on non-XY planes
Same OCCT coordinate mapping issues as CadQuery. When revolving a sketch on Plane.XZ or Plane.YZ, verify the axis parameter explicitly. The revolve axis must lie in the sketch plane.

### 6. BuildSketch face argument
When placing a sketch on a face, pass the face as the first argument to `BuildSketch`:
```python
with BuildSketch(part.faces().sort_by(Axis.Z).last):
    Circle(5)
```
The sketch origin is at the face center. Use `with Locations([(dx, dy)])` to offset.

### 7. Add() for importing geometry into BuildPart
```python
base = import_step("previous_phase.step")
with BuildPart() as part:
    Add(base)                # bring existing geometry into this context
    # now add new features...
```

### 8. Bounding box attribute names
```python
bb = part.bounding_box()
# Dimensions:
bb.size.X, bb.size.Y, bb.size.Z
# Min/max:
bb.min.X, bb.max.X
bb.min.Y, bb.max.Y
bb.min.Z, bb.max.Z
```

---

## CadQuery Coexistence

build123d and CadQuery share the OCP (OpenCASCADE) kernel. A build123d part can be wrapped for CadQuery operations:

```python
import cadquery as cq
from build123d import *

bd_part = Box(50, 30, 10)
cq_shape = cq.Shape(bd_part.wrapped)
```

This is the escape hatch for operations where CadQuery has better support (plate packing, compound assembly). Not the primary path.

---

## Script Template

```python
from build123d import *
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/scripts"))
sys.path.insert(0, str(Path.home() / ".claude/skills/novel-cad-skill/lib"))
from bd_debug_helpers import verify_boolean
from spec_format import create_spec, write_spec

# ============================================================
# PARAMETERS
# ============================================================
width = 60.0        # mm
depth = 40.0        # mm
height = 25.0       # mm
wall = 2.0          # mm
r_ext = 3.0         # mm — exterior corner fillet
clearance = 0.3     # mm — FDM clearance

# ============================================================
# SPEC
# ============================================================
spec = create_spec(
    "Example box",
    width=width, depth=depth, height=height,
    material="PLA", min_wall_mm=wall,
    engine="build123d",
)
write_spec(spec, "phase1_base.step")

# ============================================================
# MODEL
# ============================================================
with BuildPart() as part:
    Box(width, depth, height)
    Fillet(*part.edges().filter_by(Axis.Z), radius=r_ext)
    Shell(*part.faces().sort_by(Axis.Z).last, thickness=-wall)

result = part.part

# ============================================================
# EXPORT
# ============================================================
export_step(result, "phase1_base.step")
print(f"Exported: {width}x{depth}x{height}mm")
```
