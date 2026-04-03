# Frodo Doc Audit — Task #16
**Date:** 2026-04-02
**Auditor:** Frodo (NovelCAD-Main, member z0xe2w)
**Scope:** SKILL.md, SKILL_DRAFT.md, BUILD123D_REFERENCE.md cross-referenced against ARCHITECTURE.md sections 1-14

## MAJOR Issues

### gate_enforcer.py absent from SKILL.md
ARCHITECTURE.md S8 identifies "text-based gates" as the known failure mode (Rounds 1 & 3) and prescribes `gate_enforcer.py` with `GateEnforcer` class. The S12 script template imports and uses it. SKILL.md's gate protocol section is text-only — exactly the pattern S8 says doesn't work. SKILL.md script template has NO gate_enforcer import.

### context_budget.py absent from SKILL.md
ARCHITECTURE.md S9 describes `estimate_complexity(spec)` — run before Phase 1, auto-splits Phase 2 for complex parts. SKILL.md's "Complex Part Management" describes the strategy but never references the tool.

## MODERATE Issues

### fillet()/Fillet() inconsistency
SKILL.md Phase 1 example uses lowercase `fillet()` inside Builder context. BUILD123D_REFERENCE.md Gotcha #2 correctly says `Fillet()` (capitalized) with `*` unpacking. SKILL.md template contradicts the reference.

### Two SKILL docs, unclear authority
SKILL.md (12.7KB) and SKILL_DRAFT.md (25.7KB) both have identical frontmatter. Which does Claude read? SKILL_DRAFT.md is 2x the size — is it the newer version?

## MINOR Issues

- `warn_wall_mm` not in SKILL.md spec examples (ARCHITECTURE.md S6.5)
- Validator pipeline order mismatch — ARCHITECTURE.md S11 shows 14-step pipeline interleaving gate calls; SKILL.md shows only bare validator commands
- 3MF metadata fields (`export_format`, `color`, `units`, `description`) not in SKILL.md spec examples

## Clean (no issues)
- build123d mode selection guidance: consistent across all three docs
- Fallback chain (S5): matches
- Manifold as 4th validator: consistent
- "pattern" feature type (S6.1): in SKILL.md
- Sub-phase STEP import strategy: described
- CadQuery migration table in BUILD123D_REFERENCE: complete
- No CadQuery-only API patterns leaked into build123d docs
- Cross-section mandatory policy: consistent
- FDM defaults table: consistent
