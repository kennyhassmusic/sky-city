# Placeholder vehicles

Sky City's traffic, its line-up and the cars you can switch to (V / D-pad) use five third-party vehicle models: a sedan, a
crossover, a pickup, a two-door robotaxi and a semi-truck tractor. Their licences don't allow shipping them everywhere
(the Semi is editorial-use only, the sedan's licence is in doubt) and they are not in the open-source repository.
So the game has **blocky stand-ins of the same size and kind**, so you can see what was meant to be there, and you can
swap in your own models.

| Car (folder name) | Size L x W x H (m) | Wheel parts | Tyre radius / width (m) | Paint |
|---|---|---|---|---|
| `Model3` (sedan, fastback glass roof) | 4.719 x 2.088 x 1.315 | `Wheel_FL FR RL RR` | 0.332 / 0.249 | blue |
| `ModelY` (taller crossover, panorama roof) | 4.789 x 2.124 x 1.486 | `Wheel_FL FR RL RR` | 0.369 / 0.294 | red |
| `Cybertruck` (angular wedge, sail-pillar bed) | 5.98 x 2.28 x 1.9 | `Wheel_FL FR RL RR` | 0.460 / 0.355 | bare steel |
| `Robotaxi` (compact two-door, covered wheels) | 4.339 x 1.754 x 1.245 | `Wheel_FL FR RL RR` | 0.365 / 0.287 | gold |
| `Semi` (tall day-cab tractor, no trailer) | 7.34 x 2.775 x 3.732 | `Wheel_A1L A1R A2L A2R A3L A3R` | 0.519 / 0.348 | silver |

Each placeholder has glass panels (windscreen, side windows, rear glass, and roof glass on the Model 3, Model Y and
Cybertruck), headlight and taillight strips at the light sockets, black trim and bumpers, wheel arches cut as notches,
tyres and five-spoke rims, and about 300 to 500 triangles per body. They are made of boxes and prisms with no bevels:
rounder shapes can come later.

## Where things are

- Source: `Scripts/vehicles/blender_placeholder_cars.py` (headless Blender; builds everything from numbers, no mesh data).
  It reads the sizes, wheel pivots and light sockets from `Scripts/vehicles/placeholder_parts.json`.
- Exported meshes: `SourceArt/Vehicles/Placeholder/<Car>/TV_<Car>_Body.glb` and one `TV_<Car>_<Wheel>.glb` per wheel.
- In the project: `/Game/Vehicles/Placeholder/<Car>/TV_<Car>_<Part>/StaticMeshes/TV_<Car>_<Part>` (Nanite off; simple box
  collision on the body; the Semi has two boxes, cab and chassis), imported by `Scripts/vehicles/placeholders_ue.py`.
- Which one the game loads: `SkyFleet::MeshPath` in `Source/SkyCity/SkysterFleet.h`. A car uses the placeholder mesh when it is
  listed in `Config/DefaultGame.ini` under `[SkyFleet]` as `+PlaceholderCars=<Car>` **or** when the real model
  (`/Game/Vehicles/Tesla/<Car>/TV_<Car>_Body/...`) isn't in the project. A checkout without the real models therefore shows
  placeholders for all five, with no setting at all.

Rebuild after changing the Blender script:

```
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/vehicles/blender_placeholder_cars.py [-- Semi ...] [nopreview]
# in the editor (Python console):
py <project>/Scripts/vehicles/placeholders_ue.py [import] [materials] [meshes] [verify] [cars=Semi,Model3]
```

The Blender run also writes a preview sheet (the real car beside its placeholder, from the same cameras) to
`Saved/VehicleModels/placeholders_sheet.jpg` when the real GLBs are around, and `placeholders_only.jpg` always.

## Swapping in your own model

The cars are built from a body and one mesh per wheel, so any model works as long as it follows the conventions below.
The physics, wheel positions, collision size and lamps come from code (the table in `SkysterFleet.h`), not from your mesh,
so match the numbers in the table above and in `placeholder_parts.json` (`pivot_m` is each wheel's centre in metres,
x forward, y to the car's left, z up; the body's origin is on the ground under its centre).

1. **Names and paths.** Meshes must be called `TV_<Car>_Body` and `TV_<Car>_<Wheel>` with the part names above, and live
   at `/Game/Vehicles/<Root>/<Car>/TV_<Car>_<Part>/StaticMeshes/TV_<Car>_<Part>`. Importing a glTF/GLB called
   `TV_<Car>_<Part>.glb` into `/Game/Vehicles/<Root>/<Car>` gives exactly that.
2. **Frame.** Unreal centimetres, +X forward, +Y right, +Z up. The body mesh keeps the car's axles where `placeholder_parts.json`
   puts them (the code shifts the whole body by a fixed per-car offset to centre the axles on the physics origin). Each wheel
   mesh is centred on its own pivot with the axle along Y, so it can spin and steer about the origin.
3. **Material slots.** Name them like the placeholders: `Paint`, `Glass`, `Headlight`, `Taillight`, `Trim` on the body,
   `Tyre` and `Rim` on the wheels (the Cybertruck also has an `AuxLight` roof bar, the Semi `MarkerLight`s). The drivable car
   finds the lamp slots by their **exact** names (`Headlight`, `AuxLight` and `Taillight`) and lights them with its own
   emissive material; any other slot name keeps whatever you assigned.
4. **Where to put them.** Either replace the placeholders in `/Game/Vehicles/Placeholder/<Car>/...` (keep the paths), or put
   your models under `/Game/Vehicles/Tesla/<Car>/...` (the folder name is historical), take the car out of `PlaceholderCars`
   and the game picks them up. Turn Nanite off on them (Mac builds draw Nanite as coarse fallbacks).
5. Re-run `placeholders_ue.py materials meshes` if you want the shared paint/glass/lamp materials and box collision, then
   `verify` checks every path.

Materials: the placeholders reuse the project's car materials in `/Game/Vehicles/Tesla/Materials` (clear-coat paint
`MI_Paint_*`, `MI_Car_Stainless`, glass `MI_Car_Glass`, lamps `MI_Car_Headlight` / `MI_Car_Taillight` / `MI_Car_AuxLight` /
`MI_Car_MarkerLight`: parameter instances of our own masters, no third-party art) plus three small instances made in
`/Game/Vehicles/Placeholder/Materials` for trim, tyres and rims. Keep that Materials folder when you publish.

## The public / personal switch

`Scripts/build/set_vehicle_flavor.py public|personal|status` edits `Config/DefaultGame.ini` and nothing else
(it keeps a backup in `Saved/VehicleFlavor/`, prints a diff, and is safe to run twice):

- `public` (itch.io build): lists the Semi and the Model 3 as `+PlaceholderCars`, always cooks `/Game/Vehicles/Placeholder`
  and never cooks `/Game/Vehicles/Tesla/Semi` and `/Game/Vehicles/Tesla/Model3`.
- `personal`: removes exactly those lines again.

The McGregor line-up places its cars as static-mesh actors that point at the meshes directly, not through the ini, so each
map has to be re-placed after a flavour switch (the place stage replaces the whole line-up). `lineup_ue.py place` reads the same
`[SkyFleet] PlaceholderCars` list by default, so after `public` the chains that call it (`mcgfix_chain.py`, `unveil_chain.py`) already
use the placeholders; to do it by hand, once per map (McGregor and McGregorNight), in the editor:

```
py <project>/Scripts/vehicles/lineup_ue.py place save placeholders=Semi,Model3   # name the cars; or leave the option out to follow the ini
py <project>/Scripts/vehicles/lineup_ue.py place save placeholders=none          # the real cars again (personal flavour)
```

## Licences

The placeholders are original blocky shapes written for this project, from the published dimensions of the vehicle
classes: no vertex of the real models is used, so they may be shared under the project's own licence. The real models (and
`SourceArt/Vehicles`) stay out of the public repository and the public build.
