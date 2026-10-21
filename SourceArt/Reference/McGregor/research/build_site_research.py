"""Build Saved/McGregor/site_research.json: the reference dossier of the McGregor rocket test campus, one record per
facility (name, function, dates, lat/lon, map-frame x/y, footprint, height, look, OSM matches, images, sources,
confidence). The facility data live in facilities.json next to this script (hand-edited research notes); this script
adds lat/lon, OSM way ids -> mcgregor_data.json indices, oriented footprint boxes measured from the OSM rings, and the
image list from research/_sources.json, then writes the JSON and research/sources.txt.
Map frame (same as Scripts/mcgregor/build_mcgregor_data.py): metres, x east, y north, origin lat 31.40375 lon -97.4621,
x = (lon - LON0) * 95013.4785, y = (lat - LAT0) * 110574.0. Unreal: X = y*100, Y = x*100 (cm).
Run: python3 -I SourceArt/Reference/McGregor/research/build_site_research.py"""
import json, math, pathlib, datetime, sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE / "tools"))
import osm_index  # noqa: E402

LAT0, LON0, KX, KY = 31.40375, -97.4621, 95013.4785371064, 110574.0


def ll(x, y):
    return round(LAT0 + y / KY, 6), round(LON0 + x / KX, 6)


def obb(ring):
    """oriented bounding box of a ring: centre, length (long side), width, yaw (deg, long axis, clockwise from north)"""
    best = None
    pts = ring
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        c, s = math.cos(ang), math.sin(ang)
        us = [p[0] * c + p[1] * s for p in pts]
        vs = [-p[0] * s + p[1] * c for p in pts]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
            cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
            cx, cy = cu * c - cv * s, cu * s + cv * c
            L, Wd = u1 - u0, v1 - v0
            yaw = 90 - math.degrees(ang)
            if Wd > L:
                L, Wd, yaw = Wd, L, yaw - 90
            yaw = (yaw + 180) % 180
            best = (area, [round(cx, 1), round(cy, 1)], round(L, 1), round(Wd, 1), round(yaw, 1))
    return {"centre": best[1], "length_m": best[2], "width_m": best[3], "long_axis_bearing_deg": best[4]}


def main():
    fac = json.load(open(HERE / "facilities.json"))
    table, _ = osm_index.build()
    D = json.load(open(ROOT / "Saved/McGregor/mcgregor_data.json"))
    osm = {(e["type"], e["id"]): e for e in json.load(open(ROOT / "SourceArt/osm/mcgregor.json"))["elements"]}
    srcs = json.loads((HERE / "_sources.json").read_text()) if (HERE / "_sources.json").exists() else []
    out = []
    for f in fac["facilities"]:
        r = dict(f)
        x, y = f["x"], f["y"]
        if x is None or y is None:
            r["lat"] = r["lon"] = None
            r["unreal_cm"] = None
        else:
            r["lat"], r["lon"] = ll(x, y)
            r["unreal_cm"] = {"X": round(y * 100), "Y": round(x * 100)}
        m = []
        for oid in f.get("osm", []):
            typ, i = ("node", int(oid[1:])) if str(oid).startswith("n") else ("way", int(oid))
            e = osm.get((typ, i))
            hit = table.get((typ, i))
            rec = {"osm": f"{typ}/{i}", "tags": (e or {}).get("tags", {})}
            if hit:
                rec["data_list"], rec["data_index"] = hit
                item = D[hit[0]][hit[1]]
                if "ring" in item:
                    rec["footprint_obb"] = obb(item["ring"])
                elif "r" in item:
                    rec["tank"] = {"centre": item["p"], "r_mean_m": item["r"], "note": "r = mean centroid distance of the OSM ring; elongated rings (horizontal tanks / tank rows) give inflated r"}
                elif "p" in item:
                    rec["point"] = item["p"]
            m.append(rec)
        r["osm_matches"] = m
        pref = f["id"] + "/"
        r["images"] = [{"file": "SourceArt/Reference/McGregor/research/" + s["file"], "url": s["url"], "page": s["page"], "date": s["date"], "note": s["note"]}
                       for s in srcs if s["file"].startswith(pref) or s["file"] in f.get("extra_images", [])]
        out.append(r)
    res = {"title": "McGregor rocket development and test campus: reference dossier for the Sky City McGregor map",
           "updated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "status": fac.get("status", ""),
           "frame": "metres, x east, y north, origin lat 31.40375 lon -97.4621 (x=(lon-LON0)*95013.4785, y=(lat-LAT0)*110574.0); Unreal X=y*100, Y=x*100 cm; same as Saved/McGregor/mcgregor_data.json",
           "imagery_dates": fac.get("imagery_dates", {}),
           "confidence_scale": fac.get("confidence_scale", {}),
           "campus_map": "SourceArt/Reference/McGregor/research/campus_map.png",
           "notes_file": "side-session-notes/local_f02bf719-28df-48f0-bd9c-2518f43e2392/mcgregor-research-2026-10-20.md",
           "facilities": out,
           "roads": fac.get("roads", []),
           "open_questions": fac.get("open_questions", []),
           "sources": fac.get("sources", [])}
    (ROOT / "Saved/McGregor/site_research.json").write_text(json.dumps(res, indent=1))
    # sources.txt
    lines = ["McGregor research images: every file under research/, with its source URL and date.",
             "Reference only: never textures in the game, never in Content/. Copyright stays with the credited owners;",
             "NAIP (USDA) and USGS imagery are public domain; TxGIO StratMap 2020 orthoimagery is public data (credit:",
             "Texas Geographic Information Office and partners). News photos are (c) their photographers/publishers.", ""]
    for s in sorted(srcs, key=lambda s: s["file"]):
        lines.append(f"{s['file']}\n    image: {s['url']}\n    page:  {s['page']}\n    date:  {s['date']}   retrieved {s['retrieved']}   {s['saved_px'][0]}x{s['saved_px'][1]} px, {s['kb']} KB\n    note:  {s['note']}\n")
    (HERE / "sources.txt").write_text("\n".join(lines))
    print("facilities", len(out), "images", len(srcs))


if __name__ == "__main__":
    main()
