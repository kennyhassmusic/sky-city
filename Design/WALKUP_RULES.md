# Chicago storefront walk-ups: the rule set

Late-1800s to 1920s Chicago mixed-use walk-ups, as `Scripts/city/walkup.py` builds them for every
`brick_walkup` building of the generated city. The numbers live in `walkup.RULES` (metres);
`Scripts/city/test_walkup.py` checks them. Unreal units are centimetres.

## 1. Proportions

| Part | Rule | In `RULES` |
|---|---|---|
| Lot | 25 ft lot, facade 20-25 ft (6.1-7.6 m); an end lot may be a double lot | `lot_w`, `double_lot_*` |
| Bays | 2 bays of 3-3.7 m, or 3 of 2.1-2.45 m | `walkup._lot` (`bays`) |
| Ground floor | 13-15 ft (4.0-4.6 m), 25-40% taller than the floors above | `ground_h`, `ground_ratio` |
| Upper floors | 10-11 ft (3.05-3.35 m); the top floor the same or 6 in shorter | `upper_h`, `top_shorter` |
| Upper windows | about 3 x 6 ft, 1:2; sill 30-36 in above the floor; head 12-18 in below the ceiling | `window_w`, `window_aspect`, `sill_above_floor`, `head_below_ceiling` |
| Recess | 4-8 in (glass 15 cm behind the wall face). Not negotiable | `recess` |
| Window-to-wall | upper front 20-30%; storefront 70-85% glass; side walls 0-10% (party walls blind) | follows from the above |
| Storefront | bulkhead 18-30 in, display glass 7-8 ft, transom 18-36 in, sign band 24-36 in | `bulkhead`, `display`, `transom`, `sign_band` |
| Shop entry | recessed 3-5 ft, with a step | `entry_w`, `entry_depth`, `entry_step` |
| Stair door | its own narrow door, about 3 ft, at one side of the storefront | `stair_door_w` |
| Sills and lintels | stone, 1-2 in proud, 4-6 in past the jambs; lintels 8-12 in tall | `sill`, `lintel` |
| Cornice | 18-36 in proud, 2-4 ft tall; pressed metal or corbelled brick (or a stone cornice) | `cornice_h`, `cornice_proud` |
| Storefront cornice | thinner, 6-12 in proud, at the sign band | `sf_cornice` |
| Front parapet | 2-4 ft above the roof deck, sometimes taller at a central name plaque | `parapet`, `plaque*` |

## 2. What varies and what stays

**Per lot (each lot is its own building):** brick tone (red, brown, buff, cream, clinker), cornice
(bracketed metal, corbelled brick, stone), lintel (flat, segmental arch, keystone), window type
(1/1, 2/2, or vinyl replacements with the transom filled in), an oriel bay on the upper floors
(about 40%, 2-3 ft proud), storefront condition (original, remuddled, boarded), paint, sign,
awning, roll-down or accordion gate, floors (1-4, now and then a vacant lot), parapet height.

**Within one lot:** one front brick; one window type per floor; windows stacked; sills aligned per floor.

**Along the block:** zero setback (fronts on the lot line, storefronts at the sidewalk, no stoops);
flat roofs; common brick (salmon, tan and grey mixed) on the sides and the rear.

No two lots within four lots share brick + cornice + floors + storefront; neighbours differ in
brick and their tops differ by at least 30 cm.

## 3. Roof and rear

- Flat roof, dark membrane with seams and patches.
- The cornice returns 1-3 ft around a side that shows, then stops (a false front). Side parapets
  step down toward the rear in 2-4 steps; coping on every parapet.
- Roof clutter, 3-5 items, off-centre, mostly toward the rear: chimneys on the party walls with clay
  flue caps, vent stacks, a roof hatch near the stair, a skylight, 1-2 small condensers, a satellite
  dish, an old antenna mast.
- Wooden back porches with stairs on every floor.
- **Never:** rooftop water tanks (New York, not Chicago), big commercial HVAC units.

## 4. Fake tells and the fix

| Tell | Fix |
|---|---|
| Windows flush with the wall | 15 cm recess and a visible sill |
| The same building repeated | brick, cornice, lintel, bays and storefront per lot; no combination repeated within 4 lots |
| Rooflines all level | 1-4 floors, parapet 0.6-1.2 m; 1-storey neighbours and vacant lots |
| Front ornament on every side | ornament on the front only; sides in plain common brick |
| Windows on party walls | blind side walls, a few small windows at the rear |
| Tiling brick | 2.4 m brick tiles with per-brick tint, patchiness, a darker mortar on common brick |
| Everything clean | streaks under sills, soot under the cornice, patched brick, ghost signs on side walls |
| Storefront as tall as an upper floor | ground floor 25-40% taller |
| Shop and flats share a door | separate stair door |
| Every window the same | blinds, curtains, AC units, lit or dark rooms per window |
| Building floats | bulkhead on the sidewalk, a step at the recessed entry |
| Empty or symmetric roof | 3-5 items, off-centre, toward the rear |

## 5. Screenshot checklist (pass/fail)

Proportions
- [ ] Ground floor visibly taller than the upper floors.
- [ ] Facade width reads as 20-25 ft per lot.
- [ ] Upper windows tall and narrow, about 1:2, stacked.

Depth and trim
- [ ] Windows recessed, with lintels and sills.
- [ ] Cornice projects and casts a shadow.
- [ ] Storefront has bulkhead, glass, transom and sign band.
- [ ] Recessed store entry and a separate upstairs door.

Materials and ornament
- [ ] Front brick differs from the side and rear common brick.
- [ ] Ornament stops 1-3 ft around the corner.
- [ ] Party walls mostly blind.

Roof and rear
- [ ] Parapet rises above the roof.
- [ ] Side parapets step down toward the rear.
- [ ] Roof has 3-5 clutter items.
- [ ] No water tank.
- [ ] Rear porches present.

Variety
- [ ] No two adjacent buildings share brick, cornice, height and storefront.
- [ ] Rooflines vary along the block.

Wear
- [ ] Weathering: streaks, soot, patches.
- [ ] Window interiors vary.
- [ ] No visible texture tiling at 20 m.
