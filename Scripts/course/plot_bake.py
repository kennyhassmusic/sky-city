"""Draw a course bake (the JSON from ASkyCourseTrack::TestBuildJson, as saved by track_test.py) as a PNG: the deck from
above (edges and centre line, coloured by segment kind, the jump gaps in red) and a height profile along the route.
    python3 Scripts/course/plot_bake.py Saved/Playtest/course_geo/geo_build.json [build index] [out.png]"""
import json, math, sys
from PIL import Image, ImageDraw

KIND_COL = {"piece": (60, 60, 60), "split_lead": (30, 120, 220), "merge_lead": (150, 60, 200), "merge_trunk": (20, 160, 120),
            "close_link": (220, 140, 20)}


def main():
    src = sys.argv[1]
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = sys.argv[3] if len(sys.argv) > 3 else src.replace(".json", f"_{idx}.png")
    d = json.load(open(src))
    b = d["builds"][idx] if "builds" in d else d
    segs = b["segs"]
    pts = [p for s in segs for p in s["path"]]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = 15
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    W = 1400
    sc = W / max(x1 - x0, y1 - y0)
    H = int((y1 - y0) * sc) if (y1 - y0) * sc > 200 else 200
    prof_h = 260
    img = Image.new("RGB", (int((x1 - x0) * sc) + 1, H + prof_h + 30), (245, 243, 236))
    dr = ImageDraw.Draw(img)

    def P(x, y):  # course x right, course y up
        return ((x - x0) * sc, H - (y - y0) * sc)

    for si, s in enumerate(segs):
        col = KIND_COL.get(s["kind"], (0, 0, 0))
        path = s["path"]
        for k in range(len(path) - 1):
            a, c = path[k], path[k + 1]
            f = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = math.sqrt(sum(v * v for v in f)) or 1
            f = tuple(v / n for v in f)
            u = (a[3], a[4], a[5])
            # left = up x forward
            l = (u[1] * f[2] - u[2] * f[1], u[2] * f[0] - u[0] * f[2], u[0] * f[1] - u[1] * f[0])
            w = a[6] * 0.5
            deck = a[7] > 0.5 and c[7] > 0.5
            if deck:
                for sg in (1, -1):
                    p1 = P(a[0] + l[0] * w * sg, a[1] + l[1] * w * sg)
                    p2 = P(c[0] + l[0] * w * sg, c[1] + l[1] * w * sg)
                    dr.line([p1, p2], fill=col, width=2)
            dr.line([P(a[0], a[1]), P(c[0], c[1])], fill=(200, 30, 30) if not deck else (180, 180, 180), width=1)
        if path:
            m = path[len(path) // 2]
            dr.text(P(m[0], m[1]), str(si), fill=(0, 0, 0))
    for g in b.get("gates", []):
        x, y = P(g["p"][0], g["p"][1])
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(0, 0, 0), fill=(255, 220, 0))
    # height profile along lap 1's route
    route = (b.get("routes") or [list(range(len(segs)))])[0]
    prof = []
    s_acc = 0
    last = None
    for sid in route:
        for p in segs[sid]["path"]:
            if last:
                s_acc += math.dist(p[:3], last[:3])
            prof.append((s_acc, p[2], p[7] > 0.5, p[5]))
            last = p
    if prof:
        zmin = min(p[1] for p in prof) - 1
        zmax = max(p[1] for p in prof) + 1
        smax = prof[-1][0] or 1
        top = H + 20
        for k in range(len(prof) - 1):
            a, c = prof[k], prof[k + 1]
            pa = (a[0] / smax * (img.width - 20) + 10, top + prof_h - (a[1] - zmin) / (zmax - zmin) * prof_h)
            pc = (c[0] / smax * (img.width - 20) + 10, top + prof_h - (c[1] - zmin) / (zmax - zmin) * prof_h)
            dr.line([pa, pc], fill=(30, 30, 30) if a[2] else (220, 30, 30), width=2)
        dr.text((10, top), f"height {zmin:.1f}..{zmax:.1f} m over {smax:.0f} m (lap 1 route)", fill=(0, 0, 0))
    dr.text((10, 10), f"{b.get('file', '').split('/')[-1]}  valid={b.get('valid')}  length={b.get('length', 0):.0f} m  segs={len(segs)}", fill=(0, 0, 0))
    img.save(out)
    print(out)


if __name__ == "__main__":
    main()
