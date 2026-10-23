# Road layer

The city generator sits on this layer. Stage 1 dresses roads that already exist.
Stages 2–4 are the slots underneath it. They are not built.

## Stage 1 — street dressing (this module)

`dressing.py` reads centreline roads and the cross-section from `profiles.py`.

- Lamp posts, benches, bins and hydrants stay in the city streetscape.
- This stage adds traffic signals at a crossing of two major roads, stop signs
  on a lesser street, yield signs where a collector meets an arterial, and
  street-name blades. Words are the road's own name or a generic label.
- Markings: double yellow (the centre line), dashed lane lines and stop bars
  already in the streetscape, plus turn arrows, crosswalks (already there),
  a keep-clear box, and parking-stall ticks.
- Street-parking cars sit in those stalls. A lot tier's cars-per-100 m wins
  when a lot is nearby; otherwise the block uses a mid rate.
- Bus stops on collector and arterial sidewalks. The sign says BUS.
- Wear is one number per district, from the district or the average of its
  lot tiers, stamped on paint and props (faded paint, grime). Same seed, same
  output. No real brand names.

## Stage 2 — road graph

Not built. Replace the flat centreline list with a graph the dresser already
knows how to read: an edge id, a polyline, a type, and intersection nodes.

- Edge types: local, collector, arterial, with the section rules that live in
  `profiles.py` today.
- Intersection nodes own the curb return, the crosswalk, and the signal,
  instead of each edge guessing from a shared endpoint.
- Medians and two-way left-turn lanes become edge attributes, not a special
  case buried in the section builder.
- The city generator asks the graph for a face when it cuts a block. It does
  not invent the intersection.

## Stage 3 — highways

Not built. New edge types on the same graph.

- Highways, ramps, and interchanges (merge, diverge, a simple diamond).
- Shoulders instead of parking. No stall ticks and no bus stop on a highway
  edge; stage 1 already skips those ranks.
- Ramp meters and gore paint are markings on the ramp edges. The dresser
  gains a highway profile; it does not grow a second street model.

## Stage 4 — grade separation

Not built. More edge types, still one dresser.

- Rail and subway, including a station as a node rather than a building hack.
- Tunnels and cuts: an edge with a vertical clearance, so the street section
  can drop the sidewalk and the trees.
- Pedestrian bridges between sidewalks, as a short edge the dresser lights
  and names, not a one-off prop.

When a later stage lands, `dress()` should keep its signature: roads in,
props and markings out. The city generator should not grow a second copy of
these rules.
