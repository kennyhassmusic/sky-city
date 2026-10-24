# Building Builder Backlog

Logged 2026-10-24 at walk-up sign-off (tag `walkup-signoff`, commit c1cee62).

## Known issues (walk-up, non-blocking)
1. **DELI storefront reads as a flat dark slab.** Lot `b_lot_osm_22_lot1` has no shop glass, door or interior. It likely missed the pass-2 shop-interior step. Check every walk-up lot gets a modelled interior.
2. **Red brick reads tan or beige.** This is worst in shade. The fix belongs in the shared brick textures (albedo saturation and hue), not in grading. It's a shared-pipeline item, so it benefits every building type.
3. **Side parapet steps (checklist item 12) are weak.** The steps only read up close. Make them deeper or higher-contrast.

## Mechanic: store naming and categorization (separate builder system)
Goal: storefront names and types feel like a real city, with no visible repeats or neighbouring duplicates from the player's view.
- **Store catalog:** a data table of fictional store names grouped by category (food, laundry, hardware, bar, clothing, services, vacant and so on). Each entry carries its weight, any era or style tags, and the building types it fits. No real company names or logos.
- **Distribution algorithm:**
  - No two identical names within a set radius, or within the same view cone or street segment. Larger radius for distinctive names, smaller for generic ones.
  - Each category has a minimum spacing, so there are no three delis in a row, but believable clustering is allowed.
  - Category weights by district (Loop, residential, industrial edge).
  - A blue-noise or Poisson-style assignment with deterministic seeding, so reruns give identical output.
  - A validation pass that reports any name or category conflicts visible from street cameras.
- **Shared across types:** walk-ups, condos with ground retail, tower lobbies and industrial fronts all draw from the same catalog and checker.
- **Status:** not started. Build after the type passes or alongside them, owned by the shared pipeline on the main Mac.
