"""McGregor test-site layout -> Saved/McGregor/site_features.json (read by site_ue.py and by build_mcgregor_ue.py's
buildings / site stages).

What it holds (local metres: x east, y north, origin = facility centre, z above the map datum, bearings 0 = north,
90 = east):
  features    each labelled facility from Kenny's pictures (SourceArt/Reference/McGregor) matched to its OSM footprint
              and the NAIP aerial: name, which picture/label, position, size, look, the kit model that stands for it,
              confidence, and (when Saved/McGregor/site_research.json from the research agent exists) its notes.
  placements  kit meshes (Scripts/mcgregor/blender_site_kit.py) with position, bearing of the kit's front, scale,
              ground height (from the USGS DEM the terrain was built from: bilinear on Saved/McGregor/terrain_*.f32),
              collision kind (complex / box / none)
  osm_filter  what the generic OSM pass must leave out because a kit model replaces it: building centroids, kinds
              ('works' site areas and 'water_tower' footprints were extruded as 22-38 m slabs), storage tanks (all now
              kit tanks: OSM's long horizontal tanks had been drawn as fat 40 m vertical cylinders), water towers
  lots        parking lots: a draped asphalt pad (grid on the DEM + 0.18 m) and parked cars / stall lines in
              placements (OSM parking polygons; the big office lot follows its mapped aisles)
  tests       (mcgregor-tests agent, 20 Oct 2026) Scripts/mcgregor/tests_layout.py: trenches cut into the terrain, blast
              aprons, caliche pads, scorch, test hardware, and the timed engine tests' sites (engine_tests_ue.py); its kit
              pieces are ordinary placements, its site-specific meshes go to Saved/McGregor/tests_meshes.json
Positions: OSM (c) OpenStreetMap contributors; heights USGS 3DEP. No company names anywhere.
Run: python3 -I Scripts/mcgregor/site_layout.py
"""
import array, json, math, os, pathlib, random, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SAVED = ROOT / "Saved/McGregor"
D = json.load(open(SAVED / "mcgregor_data.json"))
RES = SAVED / "site_research.json"
OUT = SAVED / "site_features.json"
N, STEP = 601, 4.0
_grid = {}


def ground(x, y):
    """Bilinear terrain height (m above datum) from the 4 m grids build_mcgregor_ue.py's terrain stage used."""
    i = min(max(int((x + 4800) // 2400), 0), 3)
    j = min(max(int((y + 3600) // 2400), 0), 2)
    if (i, j) not in _grid:
        a = array.array("f")
        a.frombytes(open(SAVED / f"terrain_{i}_{j}.f32", "rb").read())
        _grid[(i, j)] = a
    g = _grid[(i, j)]
    c = (x - (-4800 + i * 2400)) / STEP
    r = (y - (-3600 + j * 2400)) / STEP
    c0, r0 = min(max(int(c), 0), N - 2), min(max(int(r), 0), N - 2)
    fc, fr = min(max(c - c0, 0), 1), min(max(r - r0, 0), 1)
    a = g[r0 * N + c0] * (1 - fc) + g[r0 * N + c0 + 1] * fc
    b = g[(r0 + 1) * N + c0] * (1 - fc) + g[(r0 + 1) * N + c0 + 1] * fc
    return a * (1 - fr) + b * fr


def fwd(b):
    r = math.radians(b)
    return math.sin(r), math.cos(r)


def corners(p, bearing, L, W):
    """Footprint corners: L along the bearing (kit Y), W across (kit X)."""
    fx, fy = fwd(bearing)
    rx, ry = fy, -fx
    return [(p[0] + fx * u + rx * v, p[1] + fy * u + ry * v) for u in (-L / 2, L / 2) for v in (-W / 2, W / 2)]


def zmin(p, bearing=0.0, L=0.0, W=0.0, sink=0.15):
    pts = [p] + (corners(p, bearing, L, W) if L else [])
    return round(min(ground(*q) for q in pts) - sink, 2)


placements, features = [], []


def put(mesh, p, bearing=180.0, scale=(1, 1, 1), z=None, collide="complex", feature="", L=0.0, W=0.0, sink=0.15):
    placements.append({"mesh": mesh, "p": [round(p[0], 2), round(p[1], 2)], "bearing": round(bearing % 360, 1),
                       "scale": [round(s, 3) for s in scale], "z": z if z is not None else zmin(p, bearing, L, W, sink),
                       "collide": collide, "feature": feature})


def feat(fid, name, pictures, p, size, look, model, osm, confidence, bearing=None):
    features.append({"id": fid, "name": name, "pictures": pictures, "p": [round(p[0], 1), round(p[1], 1)], "size_m": size,
                     "bearing": bearing, "look": look, "model": model, "osm": osm, "confidence": confidence})


def bdata(name=None, near=None):
    """A building from mcgregor_data.json by name or nearest centroid -> (centroid, building)."""
    best = None
    for b in D["buildings"]:
        r = b["ring"]
        c = (sum(q[0] for q in r) / len(r), sum(q[1] for q in r) / len(r))
        if name and b.get("name") == name:
            return c, b
        if near:
            d = math.dist(c, near)
            if best is None or d < best[0]:
                best = (d, c, b)
    return (best[1], best[2]) if best and best[0] < 8.0 else (None, None)


SUPERSEDED = []


def supersede(name=None, near=None):
    c, b = bdata(name, near)
    if c:
        SUPERSEDED.append([round(c[0], 2), round(c[1], 2)])
    return c


# ------------------------------------------------------------------ first-stage test stand area (Kenny's aerial)
WT1 = (-171.0, -497.0)                # research (base; the tall tank leans in the ortho); OSM ring centre (-174.6, -502.9)
supersede(near=(-174.6, -502.9))
put("SK_WaterTower", WT1, 180.0, feature="water_tower_1")
feat("water_tower_1", "Water tower (first-stage area)", ["aerial_test_stands.jpg (white tower, left)", "aerial_numbered.jpg #2"], WT1,
     [16, 16, 84], "plain white multi-leg elevated tank, 16 m tank with rounded bottom and low cone roof, ~83 m: the tallest structure on site; no logo",
     "SK_WaterTower", "way 509691343 man_made=water_tower (was a 38 m metal box + spheroid)", "high (research: StratMap Jan 2020 shadow)")
FS = (-134.0, -577.0)                 # stage axis over the sump's north end (StratMap 2020: hold-down ring at ~(-133, -571))
TR = (-136.0, -575.0)                 # the trench liner's origin (blender_site_kit.TRENCH_O), its rim height TRENCH_RIM
RIM = 23.3
supersede("Falcon 9 first stage test stand")
put("SK_FSStand", FS, 180.0, z=RIM, collide="complex", feature="first_stage_stand")
put("SK_FSTrench", TR, 180.0, z=RIM, collide="complex", feature="first_stage_trench")
put("SK_Crane", (-124.0, -541.0), 0.0, collide="complex", feature="first_stage_stand")
feat("first_stage_stand", "Current first-stage test stand", ["aerial_test_stands.jpg (white stage beside the red crane)", "aerial_labelled.webp 'current first stage test stand'", "aerial_numbered.jpg #1"],
     FS, [30, 26, 48], "low concrete deck with white service huts and pipe racks at the north end of the deep trench, a white stage standing in its hold-down ring, a thin 72 m lattice mast beside it, red crawler crane (NSF 2021, StratMap 2020)",
     "SK_FSStand + SK_Crane", "way 925966263 'Falcon 9 first stage test stand' (19 x 10 m)", "high")
feat("first_stage_trench", "First-stage flame trench", ["aerial_test_stands.jpg (deep concrete trench in the foreground)"], (-137, -615),
     [80, 24, 16], "deep concrete pit: 16 m sump under the stage, floor ramping 62 m up to the south, widening from 22 m to 80 m",
     "SK_FSTrench (fitted to the DEM pit, rim at %.1f m)" % RIM, "OSM aeroway=flame_trench ring; USGS DEM pit", "high")
TRI = (-15.0, -548.0)
supersede("Big Tripod Test Stand")
put("SK_Tripod", TRI, 225.0, collide="complex", feature="tripod")
feat("tripod", "Former tripod first-stage test stand (Beal Aerospace, 2000)", ["aerial_test_stands.jpg (right: tripod with blue tower)", "aerial_labelled.webp", "aerial_numbered.jpg #4", "research: nsf_2019-10_header.jpg"],
     TRI, [28, 28, 67], "three banded concrete columns, triangular concrete cap ~30-34 m, rusty steel flame deflector between the legs, blue lattice access tower on top (220 ft total)",
     "SK_Tripod", "way 233582606 'Big Tripod Test Stand'", "high (height: Spaceflight Now, March 2000)", 225.0)
ST = (-40.0, -441.0)
supersede("Falcon 9 Structural Test Stand")
put("SK_StructuralStand", ST, 180.0, (1.0, 1.0, 1.2), collide="complex", feature="structural_stand")       # ~60 m (research: shadow)
feat("structural_stand", "Structural test stand", ["aerial_test_stands.jpg (blue lattice tower, centre)", "aerial_labelled.webp", "aerial_numbered.jpg #6"],
     ST, [10, 10, 60], "tall blue lattice tower with platforms and a hoist jib, tank article inside", "SK_StructuralStand",
     "way 233582607 'Falcon 9 Structural Test Stand' (was a 45 m solid box)", "high")
HG1 = (40.5, -484.7)
supersede("Hangar")
put("SK_Hangar", HG1, 156.0, (33.9 / 30, 61.7 / 60, 0.7), collide="complex", feature="hangar_fs", L=61.7, W=33.9)
feat("hangar_fs", "Hangar by the test stands", ["aerial_numbered.jpg #5", "research: nsf_2019-10_header.jpg (white walls, grey roof, blue trim)"], HG1, [34, 62, 14],
     "white metal hangar, grey gable roof, blue trim, roll-up doors", "SK_Hangar", "way 233581969 'Hangar'", "high", 156.0)
# deluge water tank and the smaller vertical tank by the water tower (OSM storage tanks)
feat("tank_farm_fs", "First-stage area tank farms", ["research: nsf_2019-10_header.jpg (long horizontal tanks, tall vertical tanks)", "NAIP"], (-40, -490), [60, 60, 14],
     "white horizontal tanks (two 41 m, two 27 m, five 12 m), small vertical cryo tanks, a 22 m water tank", "SK_TankH / SK_TankV / SK_TankBig",
     "OSM storage_tank ways (shape -> horizontal or vertical)", "high")

# ------------------------------------------------------------------ offices, hangars, boneyard, blockhouse (labelled aerial)
SHOP = (263.4, -1634.5)
supersede("SpaceX Central Shop")
put("SK_Shop", SHOP, 147.0, (38.8 / 20, 92.0 / 40, 1.15), feature="offices_shops", L=92.0, W=38.8)
OC = (319.0, -1688.5)
supersede(near=(315.0, -1693.0))
put("SK_Hangar", OC, 57.0, (26.0 / 30, 67.5 / 60, 0.85), feature="old_core_hangar", L=67.5, W=26.0)      # full-height door on the east end
supersede(near=(289.0, -1679.0))
put("SK_Shop", (290.4, -1676.9), 237.0, (25.0 / 20, 37.7 / 40, 1.0), feature="old_core_hangar", L=37.7, W=25.0)
feat("offices_shops", "Site offices / shops", ["aerial_labelled.webp 'offices/shops'", "aerial_numbered.jpg #15"], SHOP, [39, 92, 9],
     "long white office and shop building, window bands, roll-up doors, the big parking lot to its west", "SK_Shop", "way 233581960 (central shop)", "high", 147.0)
feat("old_core_hangar", "Old core storage hangar", ["aerial_labelled.webp 'old core storage hangar'", "aerial_numbered.jpg #16"], OC, [24, 68, 17],
     "tall white hangar at the south-east end of the office complex, long axis NE-SW, full-height sliding door on its east end", "SK_Hangar + SK_Shop (office wing)", "ways 509693382, 509693383", "medium-high", 57.0)
HG3 = (211.3, -1539.0)
supersede(near=(215.0, -1540.0))
put("SK_Hangar", HG3, 147.0, (21.8 / 30, 28.9 / 60, 0.6), feature="shop_hangar_north", L=28.9, W=21.8)
feat("shop_hangar_north", "Small hangar north of the offices", ["StratMap 2020 (white gabled hangar)"], HG3, [22, 29, 12], "white gabled metal hangar", "SK_Hangar (scaled)",
     "way 233581958", "medium", 147.0)
NC = (47.7, -1463.6)
supersede(near=(52.0, -1466.0))
put("SK_Hangar", NC, 273.0, (26.4 / 30, 79.1 / 60, 1.0), feature="new_core_hangar", L=79.1, W=26.4)
feat("new_core_hangar", "New core (stage) storage hangar", ["aerial_labelled.webp 'new core storage hangar'", "aerial_numbered.jpg #8"], NC, [26, 79, 20],
     "large white hangar, big door on the west end beside the boneyard", "SK_Hangar", "way 847218461", "high", 273.0)
BH = (445.4, -1434.0)
supersede("Control Room")
put("SK_Blockhouse", BH, 237.0, (34.4 / 34, 11.6 / 12, 1.0), feature="blockhouse", L=11.6, W=34.4)
feat("blockhouse", "Blockhouse / control", ["aerial_labelled.webp 'blockhouse'", "aerial_numbered.jpg #11"], BH, [34, 12, 5],
     "low hardened concrete control building, earth berms, antenna, parking to the west", "SK_Blockhouse", "way 233581976 'Control Room'", "high", 237.0)
rnd = random.Random(7)
deb = []
for row in range(4):
    for k in range(5):
        x, y = -102.0 + row * 17.0 + rnd.uniform(-1.5, 1.5), -1336.0 - k * 16.0 + rnd.uniform(-2, 2)
        if rnd.random() < 0.8:
            put("SK_StageDebris", (x, y), rnd.choice((0.0, 180.0)) + rnd.uniform(-6, 6), (1, rnd.uniform(0.6, 1.1), 1), feature="boneyard", sink=0.05)
feat("boneyard", "Boneyard (early test-vehicle debris)", ["aerial_labelled.webp 'bone yard'", "aerial_numbered.jpg #7"], (-70, -1370), [214, 115, 4],
     "rows of scorched white stage sections and tanks lying on blocks on a gravel yard", "SK_StageDebris", "way 925912169 scrap_yard", "medium")

# ------------------------------------------------------------------ engine stands
for nm, p, s in (("Merlin Engine Dual Test Stand", (547.0, -1284.0), (1.0, 1.0, 1.25)), (None, (543.0, -1270.0), (0.9, 0.9, 1.15)),
                 ("Upper Stage Test Stand", (550.0, -1304.0), (1.2, 1.2, 1.5)), ("MVac Stand", (557.5, -1333.4), (0.8, 0.8, 1.2))):
    supersede(nm, None if nm else p)
    put("SK_EngineStandV", p, 90.0, s, collide="complex", feature="m1d_stands", L=10, W=10)    # exhaust east into the big concrete deflector apron (StratMap 2020)
feat("m1d_stands", "Engine test stands (vertical engine stands, vertical stage-2 stand, horizontal stand)", ["aerial_labelled.webp 'M1D test stand', 'stage 2 test stand'", "aerial_numbered.jpg #12 #13 #14"],
     (545, -1300), [40, 80, 25], "grey steel stand towers on concrete flame buckets, white run tanks, exhaust east into a big dark concrete deflector apron draining south to a lined basin, a black open-top water tank at (506, -1335)",
     "SK_EngineStandV x4, SK_TankOpen", "ways 233583231/2/3/4", "medium (the horizontal M1D stand of the 2015 labels is not placed: its footprint is unclear)")
S2 = (992.0, -700.0)
supersede("Test stand Falcon 9 second stage")
# (mcgregor-tests, 20 Oct: the stand over the trench head is now tests_layout.py's SK_VertStand + SK_UpperStage, the
# trench a cut pit; SK_EngineStandV's own deflector and apron would have floated over that pit)
WT2 = (1060.0, -672.0)                # research; OSM ring centre (1061.6, -684.4)
supersede(near=(1061.6, -684.4))
put("SK_WaterTowerSmall", WT2, 180.0, feature="stage2_stand")
feat("stage2_stand", "Second-stage test stand (newer) and its water tower", ["aerial_numbered.jpg #10 'new test site'", "research: nsf_2019-10_new_second_stage_stand_construction.jpg"],
     S2, [14, 14, 18], "elevated deck and mount ring over a narrow trench running SSE, white 42 m water tower east of it", "SK_EngineStandV (scaled), SK_WaterTowerSmall",
     "way 925875206, water tower way 925875205", "medium-high", 172.0)
RV = (-90.7, 328.3)
supersede("Raptor vertical test stand")
# (mcgregor-tests, 20 Oct: the vertical stand now stands on its trench head at (-112, 335), where NAIP 2022 / Esri 2025
# show it, ~20 m west of the OSM outline: tests_layout.py's SK_VertStand + SK_RaptorEngine over a cut pit)
supersede("Raptor horizontal test stand")
for p in ((-97.0, 447.0), (-80.0, 450.0)):
    put("SK_EngineStandH", p, 355.0, (1.1, 1.0, 1.0), collide="complex", feature="raptor_stands", L=14, W=15)
feat("raptor_stands", "Engine development area: vertical stand with trench, twin horizontal stands", ["aerial_numbered.jpg #3", "research: nsf_2019-10_two_horizontal_raptor_stands.jpg", "research: nsf_2025-08_raptor_north_bay_r3.jpg"],
     (-88, 400), [380, 290, 25], "horizontal stands fire north into a fan of scorch, vertical stand fires into a trench to the south; black steel cells, white tanks",
     "SK_EngineStandV, SK_EngineStandH x2", "ways 926002314, 926002320 (the 'works' area outline had been extruded into a 373 x 285 x 22 m slab)", "medium")
SD = (-748.0, -1203.8)
supersede("Super Draco test stand")
put("SK_EngineStandH", SD, 260.0, (0.8, 0.8, 1.0), collide="complex", feature="superdraco", L=10, W=9)
feat("superdraco", "Thruster test stand (west)", ["aerial_numbered.jpg #9 (thruster stands; the labelled cluster is the Dragon processing area at (190, -1060))"], SD, [13, 8, 5],
     "small horizontal thruster stand with tanks", "SK_EngineStandH (0.6)", "way 925915307", "low-medium")
supersede(near=(-686.0, -1709.0))
put("SK_StructuralStand", (-685.6, -1708.4), 180.0, (0.45, 0.45, 0.6), collide="complex", feature="west_pad_tower")
feat("west_pad_tower", "Lattice tower at the former vertical-takeoff test pad (SW)", ["aerial_labelled.webp 'grasshopper that way'"], (-685.6, -1708.4), [4, 4, 30],
     "lattice tower beside a concrete pad", "SK_StructuralStand (scaled 0.45 / 0.6)", "way 925915303 man_made=tower (was a 45 m solid box)", "low")
# research extras: the 2025 Raptor North / South horizontal stands (positions from 2025 imagery, no heights: estimates),
# the low-confidence horizontal Merlin stand, the Raptor assembly building east of the unveil lot
for nm, p in (("raptor_north_stand", (907.0, 637.0)), ("raptor_south_stand", (882.0, 212.0))):
    # (mcgregor-tests, 20 Oct: the stands, tanks, trenches, aprons and pads are now placed by tests_layout.py: they are
    # VERTICAL single-engine cells over trenches opening west (NSF Aug 2025 flyover), tanks east-west (Esri 2025))
    feat(nm, nm.replace("_", " ").capitalize() + " (2025)", ["research: nsf_2025-08_raptor_north_bay_r3.jpg", "tests: Esri 2025-04-13, NSF Aug 2025 flyover, Apple 2025-26"], p, [195, 125, 16],
         "black steel vertical engine cell over a trench opening west onto a concrete blast apron, caliche pad, white ~40 m horizontal tanks east",
         "SK_RaptorCell + SK_RaptorEngine + SK_T_Trench / Apron / Pad + SK_TankH x3 (tests_layout.py)",
         "none (newer than OSM)", "medium position, height estimated", 270.0)
supersede(near=(575.0, -1034.7))
put("SK_EngineStandH", (578.0, -1040.0), 90.0, (0.8, 0.8, 1.0), collide="complex", feature="merlin_horizontal_stand", L=32, W=12)
feat("merlin_horizontal_stand", "Horizontal Merlin stand (2015 label #12)", ["aerial_numbered.jpg #12", "site_research.json (low confidence)"], (578, -1040), [12, 10, 10],
     "small horizontal engine cell beside the tank row", "SK_EngineStandH (0.8)", "way 233582617", "low", 90.0)
RA = (2501.1, 586.5)
supersede(near=(2517.0, 587.0))
put("SK_Shop", RA, 78.0, (31.5 / 20, 161.1 / 40, 1.3), feature="raptor_assembly", L=161.1, W=31.5)
feat("raptor_assembly", "Engine assembly building (east)", ["site_research.json raptor_assembly_building"], RA, [31, 161, 11], "long white single-storey factory", "SK_Shop (scaled)",
     "way 1531097407 (was a 6 m box)", "high position, height estimated", 78.0)
HG2 = (1699.2, 572.1)
supersede(near=(1700.0, 567.0))
put("SK_Hangar", HG2, 168.0, (49.7 / 30, 90.1 / 60, 1.1), feature="hangar_east", L=90.1, W=49.7)
feat("hangar_east", "Large hangar south-west of the unveil lot", ["NAIP (white roof, long west shadow)"], HG2, [50, 90, 18],
     "large white hangar with a lower annex on its west side and a car park along the road", "SK_Hangar", "way 847218450 building=hangar (was a 6 m box)", "medium-high", 168.0)

# ------------------------------------------------------------------ every OSM storage tank as a kit tank (shape decides)
OSM = json.load(open(ROOT / "SourceArt/osm/mcgregor.json"))["elements"]
RAS = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))   # raw USGS / NAIP rasters (fetch_rasters.py)
RM = json.load(open(RAS / "rasters.json"))


def mrect(g):
    best = None
    for a10 in range(0, 1800, 5):
        r = math.radians(a10 / 10)
        c, s = math.cos(r), math.sin(r)
        us = [p[0] * c + p[1] * s for p in g]
        vs = [-p[0] * s + p[1] * c for p in g]
        ar = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or ar < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (ar, a10 / 10, max(us) - min(us), max(vs) - min(vs), (cu * c - cv * s, cu * s + cv * c))
    _, a, L, W, ctr = best
    if W > L:
        L, W, a = W, L, a + 90
    return ctr, L, W, (90 - a) % 180


ntank = {"V": 0, "Big": 0, "H": 0}
for e in OSM:
    t = e.get("tags", {})
    if e["type"] != "way" or t.get("man_made") != "storage_tank" or not e.get("geometry"):
        continue
    g = [((q["lon"] - RM["lon0"]) * RM["kx"], (q["lat"] - RM["lat0"]) * RM["ky"]) for q in e["geometry"] if q][:-1]
    c, L, W, brg = mrect(g)
    if abs(c[0]) > 4700 or abs(c[1]) > 3500:
        continue
    if L / max(W, 0.1) > 1.6 and W < 3.0 and 8.0 <= L <= 14.0:
        put("SK_TubeBank", c, brg, (1.0, L / 12.0, 1.0), feature="tanks", L=L, W=2.6, sink=0.05)      # tube-trailer banks (StratMap 2020)
        ntank["TubeBank"] = ntank.get("TubeBank", 0) + 1
    elif L / max(W, 0.1) > 1.6:
        n = max(1, int(round(W / 3.6))) if W > 6.0 else 1
        dia = max(1.6, min(W / n * (0.9 if n > 1 else 1.0), 4.6))
        fx, fy = fwd(brg)
        for k in range(n):
            off = (k - (n - 1) / 2) * W / n
            p = (c[0] + fy * off, c[1] - fx * off)
            put("SK_TankH", p, brg, (dia / 3.0, L / 10.0, dia / 3.0), feature="tanks", L=L, W=dia, sink=0.05)
            ntank["H"] += 1
    elif L <= 5.0:
        s = L / 3.4
        put("SK_TankV", c, 0.0, (s, s, max(0.7, min(1.0, s))), feature="tanks", sink=0.05)
        ntank["V"] += 1
    elif math.dist(c, (506.4, -1334.9)) < 3.0:
        put("SK_TankOpen", c, 0.0, (L / 20.0, L / 20.0, 1.0), feature="m1d_stands", sink=0.05)              # black open-top tank (StratMap 2020)
        ntank["Big"] += 1
    else:
        put("SK_TankBig", c, 0.0, (L / 20.0, L / 20.0, 1.2 if L < 18 else 1.0), feature="tanks", sink=0.05)
        ntank["Big"] += 1

# ------------------------------------------------------------------ parking lots: pads, cars, stall lines
lots = []
BODY = [("Sedan", 0.38), ("SUV", 0.34), ("Pickup", 0.28)]
PAINT = [("White", 0.30), ("Black", 0.19), ("Silver", 0.17), ("Grey", 0.18), ("Red", 0.08), ("Blue", 0.08)]


def pick(rng, table):
    v, acc = rng.random(), 0.0
    for k, w in table:
        acc += w
        if v <= acc:
            return k
    return table[-1][0]


def inside(p, ring):
    x, y, c = p[0], p[1], False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def dseg(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1e-9
    t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
    return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


def inner(p, ring, m):
    return inside(p, ring) and all(dseg(p, ring[i], ring[(i + 1) % len(ring)]) >= m for i in range(len(ring)))


def lot_pad(name, ring, step=4.0, raise_m=0.18):
    xs, ys = [q[0] for q in ring], [q[1] for q in ring]
    verts, idx, tris = [], {}, []
    gx = [min(xs) + step * k for k in range(int((max(xs) - min(xs)) / step) + 2)]
    gy = [min(ys) + step * k for k in range(int((max(ys) - min(ys)) / step) + 2)]
    for i, x in enumerate(gx):
        for j, y in enumerate(gy):
            idx[(i, j)] = len(verts)
            verts.append([round(x, 2), round(y, 2), round(ground(x, y) + raise_m, 3)])
    for i in range(len(gx) - 1):
        for j in range(len(gy) - 1):
            cx, cy = gx[i] + step / 2, gy[j] + step / 2
            if inside((cx, cy), ring):
                a, b, c, d = idx[(i, j)], idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)]
                tris += [[a, b, c], [a, c, d]]
    used = sorted({v for t in tris for v in t})
    remap = {v: k for k, v in enumerate(used)}
    lots.append({"name": name, "verts": [verts[v] for v in used], "tris": [[remap[v] for v in t] for t in tris], "raise_m": raise_m})


def pad_z(x, y, raise_m=0.18):
    return round(ground(x, y) + raise_m, 3)


def stalls_along(a, b, ring, rng, avoid, fill, feature, both=True, depth=5.4, width=2.7, aisle=6.0, margin=0.6):
    """Stalls on both sides of the aisle a->b, cars nose-in toward the aisle; lines between stalls."""
    L = math.dist(a, b)
    if L < width:
        return 0
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, ny = -uy, ux
    n = 0
    brg_aisle = math.degrees(math.atan2(ux, uy))
    for side in ((1, -1) if both else (1,)):
        off = aisle / 2 + depth / 2
        k = 0
        s = width / 2
        while s < L - width / 2:
            px, py = a[0] + ux * s + nx * off * side, a[1] + uy * s + ny * off * side
            ok = inner((px, py), ring, margin + depth / 2) and all(dseg((px, py), q0, q1) > depth / 2 + 2.6 for q0, q1 in avoid)
            if ok:
                # stall line on the near edge
                lx, ly = px - ux * width / 2, py - uy * width / 2
                put("SK_StallLine", (lx, ly), brg_aisle + 90.0 * side, (1, depth / 5.5, 1), z=pad_z(lx, ly) + 0.005, collide="none", feature=feature)
                if rng.random() < fill:
                    body, paint = pick(rng, BODY), pick(rng, PAINT)
                    face = brg_aisle - 90.0 * side + rng.uniform(-3, 3)        # nose toward the aisle
                    jitter = rng.uniform(-0.25, 0.25)
                    cx, cy = px + ux * jitter, py + uy * jitter
                    put(f"SK_Car_{body}_{paint}", (cx, cy), face + (180.0 if rng.random() < 0.15 else 0.0), z=pad_z(cx, cy) + 0.01, collide="box", feature=feature)
                    n += 1
            s += width
            k += 1
    return n


def osm_ring(wid):
    for e in OSM:
        if e["id"] == wid:
            return [((q["lon"] - RM["lon0"]) * RM["kx"], (q["lat"] - RM["lat0"]) * RM["ky"]) for q in e["geometry"] if q][:-1]


rng = random.Random(42)
cars = {}
# the big office lot (way 925912177), with its mapped aisles (OSM service ways inside it)
ring = osm_ring(925912177)
lot_pad("OfficeLot", ring)
aisles = []
for r in D["roads"]:
    if r["kind"] == "service" and r["surface"] == "asphalt":
        pts = r["pts"]
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if inside(pts[i], ring) or inside(pts[i + 1], ring)]
        aisles += segs
roads_near = []
for r in D["roads"]:
    pts = r["pts"]
    for i in range(len(pts) - 1):
        if any(math.dist(pts[i], q) < 150 for q in ring):
            roads_near.append((pts[i], pts[i + 1]))
# merge aisle segments into straight runs by bearing (the lot's long aisles run ~148 deg, the cross aisles ~57 deg)
runs = []
for a, b in aisles:
    if math.dist(a, b) < 0.5:
        continue
    brg = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 180
    if abs(brg - 148) < 20:
        runs.append((a, b))
n = 0
for a, b in runs:
    avoid = [s for s in roads_near if s != (a, b) and not (math.dist(s[0], b) < 0.1 or math.dist(s[1], a) < 0.1 or s[0] == a or s[1] == b)]
    n += stalls_along(a, b, ring, rng, avoid, 0.78, "parking_office")
cars["OfficeLot"] = n
feat("parking_office", "Main parking lot (offices)", ["aerial_labelled.webp (big lot left of the offices)", "aerial_numbered.jpg #15"], (197, -1666), [136, 85, 0],
     "light asphalt lot, rows of parked cars nose-in along NNW-SSE aisles", "draped pad SM_MG_SiteLots + SK_Car_* + SK_StallLine",
     "way 925912177 amenity=parking + its service aisles", "high")


def simple_lot(wid, name, fill, feature):
    ring = osm_ring(wid)
    lot_pad(name, ring)
    c, L, W, brg = mrect(ring)
    near = [(r, i) for r in D["roads"] if r["kind"] not in ("footway", "path") for i in range(len(r["pts"]) - 1) if math.dist(r["pts"][i], c) < L + 60]
    # service ways mapped inside the lot are its aisles: stalls along them, like the office lot
    inner_aisles = [(r["pts"][i], r["pts"][i + 1]) for r, i in near if r["kind"] == "service" and (inside(r["pts"][i], ring) or inside(r["pts"][i + 1], ring))]
    if inner_aisles:
        n = 0
        for a, b in inner_aisles:
            avoid = [(r["pts"][i], r["pts"][i + 1]) for r, i in near if (r["pts"][i], r["pts"][i + 1]) not in inner_aisles]
            n += stalls_along(a, b, ring, rng, avoid, fill, feature, margin=0.3)
        return n
    fx, fy = fwd(brg)
    a = (c[0] - fx * (L / 2 - 1.0), c[1] - fy * (L / 2 - 1.0))
    b = (c[0] + fx * (L / 2 - 1.0), c[1] + fy * (L / 2 - 1.0))
    both = W > 15.0
    avoid = [(r["pts"][i], r["pts"][i + 1]) for r, i in near]
    return stalls_along(a, b, ring, rng, avoid, fill, feature, both=both, aisle=6.0 if both else max(1.0, W - 5.4 * 2 - 1.0), margin=0.3)


cars["BlockhouseLot"] = simple_lot(925912166, "BlockhouseLot", 0.55, "blockhouse")
cars["CoreHangarLot"] = simple_lot(925912173, "CoreHangarLot", 0.6, "new_core_hangar")
cars["StandsLot"] = simple_lot(233581971, "StandsLot", 0.5, "hangar_fs")
# the car park west of the Rocket Development Hangar (way 847218453) is left out: it borders the real unveil area
# (~(1730, 700), the mcgregor-unveil agent's), which may take it over

# ------------------------------------------------------------------ test stands round 2 (mcgregor-tests agent, 20 Oct 2026)
# trenches cut into the terrain, blast aprons with exhaust soot, caliche pads, scorch, engines / stage / display booster
# on the stands, and the timed engine tests' sites: Scripts/mcgregor/tests_layout.py (its meshes -> tests_meshes.json)
import sys as _sys
_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tests_layout
TESTS = tests_layout.build(ground, put, feat)

# ------------------------------------------------------------------ keep the roads clear
# footprint (L along the bearing, W across) for the clearance check; trench / lines / lots don't stand on roads
FOOT = {"SK_Car": (4.8, 1.9), "SK_TankH": (10, 3.4), "SK_TubeBank": (12, 2.6), "SK_TankV": (3.6, 3.6), "SK_TankBig": (21, 21), "SK_TankOpen": (21, 21),
        "SK_Hangar": (61, 31), "SK_Shop": (41, 21), "SK_Blockhouse": (13, 48), "SK_Tripod": (34, 34), "SK_StructuralStand": (14, 14),
        "SK_WaterTower": (18, 18), "SK_EngineStandV": (14, 10), "SK_EngineStandH": (40, 14), "SK_Crane": (8, 5), "SK_StageDebris": (14, 3.7)}
ROADSEG = [(r["pts"][i], r["pts"][i + 1], r["w"]) for r in D["roads"] if r["kind"] not in ("footway", "path") for i in range(len(r["pts"]) - 1)]


def intrusion(p):
    key = next((k for k in FOOT if p["mesh"].startswith(k)), None)
    if key is None:
        return 0.0, None
    L, W = FOOT[key][0] * p["scale"][1], FOOT[key][1] * p["scale"][0]
    fx, fy = fwd(p["bearing"])
    rx, ry = fy, -fx
    cx, cy = p["p"]
    pts = [(cx + fx * u + rx * v, cy + fy * u + ry * v) for u in [-L / 2 + L * i / 6 for i in range(7)] for v in [-W / 2 + W * j / 4 for j in range(5)]]
    worst, seg = 0.0, None
    for a, b, w in ROADSEG:
        if math.dist(a, (cx, cy)) > 120:
            continue
        for q in pts:
            d = w / 2 - 0.3 - dseg(q, a, b)
            if d > worst:
                worst, seg = d, (a, b)
    return worst, seg


dropped, nudged = 0, []
keep = []
for p in placements:
    if p["mesh"] in ("SK_FSStand", "SK_FSTrench", "SK_StallLine") or p["mesh"].startswith("SK_T_"):
        keep.append(p)
        continue
    d, seg = intrusion(p)
    if d <= 0:
        keep.append(p)
        continue
    if p["mesh"].startswith(("SK_Car", "SK_StageDebris")):
        dropped += 1
        continue
    (ax, ay), (bx, by) = seg
    L = math.dist(seg[0], seg[1]) or 1.0
    nx, ny = -(by - ay) / L, (bx - ax) / L
    if (p["p"][0] - ax) * nx + (p["p"][1] - ay) * ny < 0:
        nx, ny = -nx, -ny
    mv = min(d + 0.5, 4.0)
    p["p"] = [round(p["p"][0] + nx * mv, 2), round(p["p"][1] + ny * mv, 2)]
    nudged.append([p["mesh"], p["feature"], round(mv, 1), round(intrusion(p)[0], 1)])
    keep.append(p)
placements[:] = keep
# stall lines whose car was dropped stay (empty stalls are normal)


# ------------------------------------------------------------------ red obstruction beacons on the tall structures (night map)
TOPS = {"SK_WaterTower": [(0.0, 0.0, 84.1)], "SK_WaterTowerSmall": [(0.0, 0.0, 45.1)], "SK_Tripod": [(0.0, 0.0, 70.2)],
        "SK_StructuralStand": [(0.0, 0.0, 53.6)], "SK_FSStand": [(-8.75, 1.75, 72.3)]}
beacons = []
for p in placements:
    for lx, ly, lz in TOPS.get(p["mesh"], []):
        if p["scale"][2] < 0.9:
            continue                       # the small west tower
        b = math.radians(p["bearing"] + 180.0)          # kit -Y faces the bearing: rotate kit (x, y) into the map
        c, s_ = math.cos(b), math.sin(b)
        sx, sy = lx * p["scale"][0], ly * p["scale"][1]
        beacons.append([round(p["p"][0] + sx * c + sy * s_, 2), round(p["p"][1] - sx * s_ + sy * c, 2), round(p["z"] + lz * p["scale"][2], 2)])


# ------------------------------------------------------------------ research agent's facts (read, never written here)
research = None
if RES.exists():
    try:
        research = json.load(open(RES))
    except Exception as ex:
        research = {"error": str(ex)}
if isinstance(research, dict):
    items = research.get("facilities") or research.get("features") or research.get("items") or []
    for f in features:
        best = None
        for r in items:
            p = r.get("xy") or r.get("map_xy") or r.get("p") or ([r.get("x"), r.get("y")] if r.get("x") is not None else None)
            if not p or p[0] is None:
                continue
            d = math.dist(p, f["p"])
            if d < 120 and (best is None or d < best[0]):
                best = (d, r)
        if best:
            r = best[1]
            f["research"] = {k: r.get(k) for k in ("name", "look", "height_m", "height", "footprint_m", "footprint", "confidence", "sources", "notes") if r.get(k) is not None}

out = {"frame": "metres, x east, y north, origin = facility centre; z above the map datum; bearing 0 = north, 90 = east (the kit's front)",
       "updated": time.strftime("%Y-%m-%d %H:%M"), "research_file": str(RES.relative_to(ROOT)) if RES.exists() else None,
       "features": features, "placements": placements,
       "osm_filter": {"buildings": SUPERSEDED, "skip_kinds": ["works", "water_tower"], "skip_tank_kinds": ["storage_tank"],
                      "water_towers": [[-174.6, -502.9], [1061.6, -684.4]]},     # the OSM centroids the spheroid towers stand on
       "lots": lots, "beacons": beacons, "tests": TESTS,
       "counts": {"placements": len(placements), "tanks": ntank, "cars": cars, "superseded_buildings": len(SUPERSEDED),
                  "road_clearance": {"dropped": dropped, "nudged": nudged}},
       "attribution": "(c) OpenStreetMap contributors; USGS 3DEP; NAIP (USDA)"}
OUT.write_text(json.dumps(out, indent=1))
print(json.dumps(out["counts"]), "rim", RIM, "->", OUT)
