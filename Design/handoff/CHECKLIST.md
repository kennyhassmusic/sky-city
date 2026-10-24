# Building-type screenshot checklist (pass/fail)

The walk-up checklist (`Design/WALKUP_RULES.md` section 5) in a type-neutral form, for every building type on
the generated city. Each type's own rules file supplies the numbers (floor heights, bay widths, window sizes,
cornice depth). This list says what must read on screen.

Grade each item **PASS**, **FAIL** or **MISSING PIECE** (the rules ask for something the kit doesn't build yet),
against shots you took yourself. Name the shot (and a crop if it's small) as evidence for each. A weak pass is a
PASS with a note.

Shots to take per type, for a few representative buildings: street (across the street, eye height), close-up,
corner (45°, showing a side wall), roofs (from the air), rear. Plus the two report cameras (`street`, `aerial`)
for the GPU numbers (`Design/handoff/HANDOFF.md` section 3).

## Proportions
- [ ] The ground floor (or base or podium) reads at the height the type's rules set relative to the floors above.
- [ ] Each building's width reads as its type's plot or bay module, not one undivided block.
- [ ] Windows have the type's proportions and stack in columns from floor to floor.

## Facade depth and trim
- [ ] Windows are recessed behind the wall face, with the type's sills, heads or frames.
- [ ] The top of the building (cornice, crown, parapet or roof edge) projects or steps and casts a shadow.
- [ ] Street-level frontage has the type's parts (for example bulkhead, glass, transom and sign band; or lobby, canopy).
- [ ] Entrances read: a recessed or marked main entry, and a separate entry where the type has one (upstairs, service).

## Materials and ornament
- [ ] The front material differs from the side and rear material where the type has a false front or party walls.
- [ ] Ornament is where the type puts it (front only on false fronts), and returns or stops believably at corners.
- [ ] Party walls and blind walls are blind, with openings only where the type allows them.

## Roof and rear
- [ ] Parapets or roof edges rise above the roof deck where the type has them.
- [ ] Side and rear roof edges step or finish the way the type's rules say.
- [ ] The roof has the type's clutter (vents, hatches, units, chimneys), at real size, legible from the air and,
      where tall enough, from the street.
- [ ] Nothing the rules forbid is on the roof (for Chicago walk-ups: no water tanks).
- [ ] The rear has the type's features (for example porches, fire escapes, loading).

## Variety
- [ ] No two adjacent buildings share the full combination of material, top, height and street frontage.
- [ ] Rooflines or tops vary along the block.

## Wear and life
- [ ] Weathering reads at street distance as streaks, drips and grime, never as dark blobs or stickers.
- [ ] Window interiors vary (blinds, curtains, units). By day no room glows without a light source; any glow is
      faint and warm.
- [ ] Shop or lobby glass is dark and slightly reflective, with the interior visible. No white slabs.
- [ ] No visible texture tiling at 20 m.

## Light and shade
- [ ] Shaded facades keep their material colour (no flat blue-grey cast).
- [ ] No light leaks onto shaded facades (no bright patches where a building's shadow should be solid).

## Signage
- [ ] Every sign and lettered decal reads the right way round (no 180° or mirrored text) and uses no real brand names.

## Budget
- [ ] The frame at the report cameras is within the last sign-off's numbers (`HANDOFF.md` section 3), allowing
      for the run-to-run spread.
- [ ] Map check: 0 errors, 0 warnings. No material compile failures after the import.
