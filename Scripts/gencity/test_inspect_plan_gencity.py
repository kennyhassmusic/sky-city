"""Plan checks for the inspection drives (no Unreal): routes never U-turn or repeat an edge, corners get fillet points,
pedestrian cameras stand off every road at their intersection, the chase camera stays under the signal heads, and
the teleport hold (inspect_gencity_ue.py's put-back) zeroes the controls and holds in game time.

Run: python3 -I Scripts/gencity/test_inspect_plan_gencity.py
"""
import math
import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inspect_plan_gencity as P


def make(nodes, edge_list, ctx=None):
    """nodes {id: (x, y)}, edge_list [(id, a, b, class)] -> nodes, edges, adj as graph() builds them, with widths."""
    edges, adj = {}, {}
    for eid, a, b, cls in edge_list:
        L = math.hypot(nodes[b][0] - nodes[a][0], nodes[b][1] - nodes[a][1])
        edges[eid] = {"id": eid, "a": a, "b": b, "class": cls, "len": L, "lanes": None}
        adj.setdefault(a, []).append(eid)
        adj.setdefault(b, []).append(eid)
    P.set_widths(edges, ctx or {})
    return nodes, edges, adj


def grid(n=4, step=100.0, cls="local"):
    nodes = {"n%d_%d" % (i, j): (i * step, j * step) for i in range(n) for j in range(n)}
    el = []
    for i in range(n):
        for j in range(n):
            if i + 1 < n:
                el.append(("h%d_%d" % (i, j), "n%d_%d" % (i, j), "n%d_%d" % (i + 1, j), cls))
            if j + 1 < n:
                el.append(("v%d_%d" % (i, j), "n%d_%d" % (i, j), "n%d_%d" % (i, j + 1), cls))
    return nodes, el


def front_all(edges, zone="residential"):
    return {e: {"zones": Counter({zone: 3}), "types": Counter(), "districts": Counter({"d": 1})} for e in edges}


def vertex_turns(pts):
    out = []
    for i in range(1, len(pts) - 1):
        a = math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])
        b = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
        out.append(abs(math.degrees(math.remainder(b - a, 2 * math.pi))))
    return out


class TestRoutes(unittest.TestCase):
    def setUp(self):
        P.BOX["d"] = []

    def test_walk_on_grid_never_reverses_or_repeats(self):
        nodes, el = grid(5)
        nodes, edges, adj = make(nodes, el)
        front = front_all(edges)
        for start in sorted(edges):
            path, _end, _total = P.walk(nodes, edges, adj, front, ("residential",), set(), start_eid=start,
                                        target=5000.0)
            self.assertEqual(P.route_problems(path, nodes, edges), [], start)
            ids = [e for e, _ in path]
            self.assertEqual(len(ids), len(set(ids)))
            for k in range(1, len(path)):
                self.assertNotEqual(path[k][0], path[k - 1][0])

    def test_dead_end_ends_the_route(self):
        # a straight street that stops: the route ends at the dead end, it doesn't turn back
        nodes = {"a": (0, 0), "b": (100, 0), "c": (200, 0)}
        nodes, edges, adj = make(nodes, [("e1", "a", "b", "local"), ("e2", "b", "c", "local")])
        path, end, _t = P.walk(nodes, edges, adj, front_all(edges), ("residential",), set(), start_eid="e1",
                               target=5000.0)
        self.assertEqual([e for e, _ in path], ["e1", "e2"])
        self.assertEqual(end, "c")
        self.assertEqual(P.route_problems(path, nodes, edges), [])

    def test_walk_avoids_a_pocket_of_dead_ends(self):
        # civic_river seed 7: a collector stem into a T whose two arms both dead-end; the old walk drove in and U-turned
        nodes = {"w": (-100, 0), "x": (0, 0), "t": (0, 100), "tl": (-100, 100), "tr": (100, 100), "s": (0, -100)}
        el = [("in", "w", "x", "local"), ("stem", "x", "t", "collector"), ("armL", "t", "tl", "local"),
              ("armR", "t", "tr", "local"), ("down", "x", "s", "local")]
        prev = "x"
        for i in range(1, 7):                    # the street east goes on
            nodes["e%d" % i] = (100.0 * i, 0.0)
            el.append(("on%d" % i, prev, "e%d" % i, "local"))
            prev = "e%d" % i
        nodes, edges, adj = make(nodes, el)
        front = front_all(edges, "other")
        front["stem"] = {"zones": Counter({"civic": 50}), "types": Counter(), "districts": Counter()}
        path, _end, _t = P.walk(nodes, edges, adj, front, ("civic",), set(), start_eid="in", target=5000.0)
        self.assertNotIn("stem", [e for e, _ in path])
        self.assertEqual(P.route_problems(path, nodes, edges), [])

    def test_route_problems_flags_u_turns_and_repeats(self):
        nodes, el = grid(3)
        nodes, edges, adj = make(nodes, el)
        uturn = [("h0_0", "n0_0"), ("h0_0", "n1_0")]
        self.assertTrue(any("U-turn" in p or "twice" in p for p in P.route_problems(uturn, nodes, edges)))
        loop = [("h0_0", "n0_0"), ("v1_0", "n1_0"), ("h0_1", "n1_1"), ("v0_0", "n0_1"), ("h0_0", "n0_0")]
        self.assertTrue(any("twice" in p for p in P.route_problems(loop, nodes, edges)))

    def test_shortest_to_bridge_never_turns_back(self):
        # the bridge is right behind the car: the legal way goes round the block, not back down the same street
        nodes, el = grid(4)
        el.append(("bridge", "n0_0", "bx", "arterial"))
        nodes["bx"] = (-100.0, 0.0)
        nodes, edges, adj = make(nodes, el)
        path = [("h0_0", "n0_0"), ("h1_0", "n1_0")]
        out = P.to_bridge(nodes, edges, adj, path, {"bridge"})
        ids = [e for e, _ in out]
        self.assertIn("bridge", ids)
        self.assertEqual(P.route_problems(out, nodes, edges), [])

    def test_ped_cams_off_every_leg(self):
        # an arterial (16 m curb to curb) crossing a parked collector (12 m) and a T with a local (11 m)
        nodes = {"c": (0, 0), "n": (0, 120), "s": (0, -120), "e": (120, 0), "w": (-120, 0), "t": (300, 0),
                 "tn": (300, 120)}
        el = [("an", "c", "n", "arterial"), ("as", "s", "c", "arterial"), ("ce", "c", "e", "collector"),
              ("cw", "w", "c", "collector"), ("ce2", "e", "t", "collector"), ("tl", "t", "tn", "local"),
              ("te", "t", "t2", "collector")]
        nodes["t2"] = (420, 0)
        ctx = {"ce": "residential", "cw": "residential", "ce2": "residential", "te": "residential", "tl": "residential"}
        nodes, edges, adj = make(nodes, el, ctx)
        self.assertAlmostEqual(edges["an"]["hw"], 8.0)
        self.assertAlmostEqual(edges["ce"]["hw"], 6.0)
        self.assertAlmostEqual(edges["tl"]["hw"], 5.5)
        for node in ("c", "t"):
            cams = P.ped_cams(node, nodes, edges, adj)
            self.assertEqual(len(cams), len(adj[node]))
            for cam in cams:
                for lid in adj[node]:
                    e = edges[lid]
                    d, _t = P._seg_dist(cam["at_plan"], nodes[e["a"]], nodes[e["b"]])
                    self.assertGreaterEqual(d, e["hw"] + P.PED_CURB_M - 0.01, (node, cam, lid))
                    self.assertFalse(P.in_strip(cam["at_plan"], nodes, e))
                # it looks down its leg: the aim point 40 m out along the leg is within 45 deg of the view
                lh = heading_of(nodes, edges[cam["leg"]], node)
                c = nodes[node]
                aim = (c[0] + math.cos(lh) * 40, c[1] + math.sin(lh) * 40)
                want = math.degrees(math.atan2(aim[0] - cam["at_plan"][0], aim[1] - cam["at_plan"][1]))
                self.assertLess(abs(math.remainder(want - cam["yaw"], 360.0)), 1.0)


def heading_of(nodes, e, start):
    return P.heading(nodes, e, start)


class TestLanePath(unittest.TestCase):
    def corner(self, turn="right"):
        # east 100 m, then a 90-degree turn (right = south, left = north)
        y = -100 if turn == "right" else 100
        nodes = {"a": (0, 0), "b": (100, 0), "c": (100, y)}
        nodes, edges, adj = make(nodes, [("e1", "a", "b", "local"), ("e2", "b", "c", "local")])
        return nodes, edges, [("e1", "a"), ("e2", "b")]

    def test_fillet_at_a_90_degree_corner(self):
        for turn in ("right", "left"):
            nodes, edges, path = self.corner(turn)
            pts = P.lane_path(path, nodes, edges)
            turns = vertex_turns(pts)
            self.assertLessEqual(max(turns), 30.0, turn)
            # the corner is an arc of several points, not one vertex
            near = [p for p in pts if math.hypot(p[0] - 100, p[1]) < 12.0]
            self.assertGreaterEqual(len(near), 4, turn)
            # dist only grows; the edge index switches once
            self.assertTrue(all(pts[i + 1][2] >= pts[i][2] for i in range(len(pts) - 1)))
            ks = [p[3] for p in pts]
            self.assertEqual(ks, sorted(ks))
            self.assertEqual(set(ks), {0, 1})
            # step size: never a jump longer than STEP_M
            for i in range(len(pts) - 1):
                self.assertLessEqual(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]), P.STEP_M + 0.01)

    def test_lane_offset_right_hand_and_consistent(self):
        for turn in ("right", "left"):
            nodes, edges, path = self.corner(turn)
            pts = P.lane_path(path, nodes, edges)
            for x, y, _d, _k in pts:
                if x < 80:                       # on e1 (eastbound): right of travel is -y
                    self.assertAlmostEqual(y, -P.LANE_M, places=6)
                elif abs(y) > 20:                # on e2: southbound right is -x (x = 100 - 1.7); northbound +x
                    want = 100 - P.LANE_M if turn == "right" else 100 + P.LANE_M
                    self.assertAlmostEqual(x, want, places=6)
            # a right turn stays in the near lanes the whole way round (never cuts toward a centre line); a left turn
            # keeps to its lane (within 0.5 m) outside the intersection box and only swings across inside it
            hw = edges["e1"]["hw"]
            for x, y, _d, _k in pts:
                if turn == "right":
                    self.assertTrue(y <= -P.LANE_M + 1e-6 and x <= 100 - P.LANE_M + 1e-6, (x, y))
                elif x < 100 - hw:
                    self.assertLessEqual(y, -P.LANE_M + 0.5, (x, y))
                elif y > hw:
                    self.assertGreaterEqual(x, 100 + P.LANE_M - 0.5, (x, y))

    def test_short_segment_limits_the_radius(self):
        # a 10 m jog: the fillets shrink to fit, no point doubles back
        nodes = {"a": (0, 0), "b": (60, 0), "c": (60, -10), "d": (120, -10)}
        nodes, edges, _adj = make(nodes, [("e1", "a", "b", "local"), ("e2", "b", "c", "local"),
                                          ("e3", "c", "d", "local")])
        pts = P.lane_path([("e1", "a"), ("e2", "b"), ("e3", "c")], nodes, edges)
        self.assertLessEqual(max(vertex_turns(pts)), 50.0)
        self.assertTrue(all(pts[i + 1][2] >= pts[i][2] for i in range(len(pts) - 1)))

    def test_build_on_grid(self):
        P.BOX["d"] = []
        nodes, el = grid(5)
        nodes, edges, adj = make(nodes, el)
        front = front_all(edges)
        path, _e, _t = P.walk(nodes, edges, adj, front, ("residential",), set(), start_eid="h0_0", target=1200.0)
        r0 = P.build("t", path, nodes, edges, adj, front, set())
        on = r0["path"][10]
        near, far = [on[0] + 1500.0, on[1]], [900000.0, 0.0]
        r = P.build("t", path, nodes, edges, adj, front, set(), masts_ue=[near, far])
        self.assertEqual(r["problems"], [])
        self.assertLessEqual(max(vertex_turns(r["path"])), 30.0)
        self.assertEqual(r["masts_ue"], [[round(near[0], 1), round(near[1], 1)]])
        for c in r["caps"]:
            if c["kind"] == "ped":
                self.assertTrue(c["cams"])
                for cam in c["cams"]:
                    for lid in adj[c["node"]]:
                        self.assertFalse(P.in_strip(cam["at_plan"], nodes, edges[lid]))


class TestChaseCam(unittest.TestCase):
    def test_under_the_signal_heads(self):
        d, e, h, tucked = P.chase_cam([0.0, 0.0], 0.0, [])
        self.assertFalse(tucked)
        self.assertLessEqual(h, P.CHASE_MAX_Z_M)
        self.assertAlmostEqual(h, P.CHASE_PIVOT_M + d * math.sin(math.radians(e)))
        # a high elevation asked for is capped
        d, e, h, _t = P.chase_cam([0.0, 0.0], 0.0, [], dist=12.0, elev=30.0)
        self.assertLessEqual(h, P.CHASE_MAX_Z_M + 1e-9)

    def test_tucks_in_near_a_mast(self):
        # a mast pole 5 m behind and 4 m left of the car (car at origin heading +X): within reach of the boom
        d, e, h, tucked = P.chase_cam([0.0, 0.0], 0.0, [[-500.0, -400.0]])
        self.assertTrue(tucked)
        self.assertLessEqual(d, P.TUCK_DIST_M)
        self.assertLessEqual(h, P.TUCK_MAX_Z_M + 1e-9)
        far = P.chase_cam([0.0, 0.0], 0.0, [[-5000.0, 3000.0]])
        self.assertFalse(far[3])


class FakeRoot:
    def __init__(self, sim=True):
        self.sim = sim
        self.lin = (5.0, 0.0, 0.0)
        self.ang = (0.0, 0.0, 30.0)

    def is_simulating_physics(self):
        return self.sim

    def set_physics_linear_velocity(self, v, add):
        assert add is False
        self.lin = v

    def set_physics_angular_velocity_in_degrees(self, v, add):
        assert add is False
        self.ang = v


class FakePawn:
    def __init__(self, sim=True):
        self.props = {"test_throttle": 1.0, "test_steer": -0.2, "test_brake": 0.0, "test_stop": 0.0,
                      "test_boost": True, "test_jump": False, "test_slide": False}
        self.root_component = FakeRoot(sim)

    def set_editor_property(self, k, v):
        self.props[k] = v

    def get_editor_property(self, k):
        return self.props[k]


class TestTeleportHold(unittest.TestCase):
    def test_reset_zeroes_controls_and_velocity(self):
        # stuck #2: full throttle, steer -0.2 at the stuck detection
        p = FakePawn()
        until = P.teleport_reset(p, 100.0, (0.0, 0.0, 0.0))
        self.assertEqual(until, 100.0 + P.HOLD_S)
        self.assertEqual(p.props["test_throttle"], 0.0)
        self.assertEqual(p.props["test_steer"], 0.0)
        self.assertEqual(p.props["test_brake"], 1.0)
        self.assertEqual(p.props["test_stop"], 1.0)
        self.assertFalse(p.props["test_boost"])
        self.assertEqual(p.root_component.lin, (0.0, 0.0, 0.0))
        self.assertEqual(p.root_component.ang, (0.0, 0.0, 0.0))

    def test_no_physics_body_is_fine(self):
        p = FakePawn(sim=False)
        P.teleport_reset(p, 0.0, (0.0, 0.0, 0.0))
        self.assertEqual(p.root_component.lin, (5.0, 0.0, 0.0))     # left to the car's own sim (SpawnAt)
        self.assertFalse(P.zero_velocity(object(), (0.0, 0.0, 0.0)))

    def test_hold_runs_in_game_time_then_steers_then_drives(self):
        until = 10.0 + P.HOLD_S
        self.assertEqual(P.hold_phase(10.0, until), "hold")
        self.assertEqual(P.hold_phase(until - 0.01, until), "hold")
        self.assertEqual(P.hold_phase(until + 0.01, until), "steer")
        self.assertEqual(P.hold_phase(until + P.STEER_IN_S + 0.01, until), "drive")
        self.assertEqual(P.hold_phase(5.0, None), "drive")

    def test_hold_controls_override_stale_input_every_tick(self):
        p = FakePawn()
        P.hold_controls(p)
        p.set_editor_property("test_throttle", 1.0)     # something stale writes throttle during the hold ...
        P.hold_controls(p)                              # ... drive() re-applies the hold the next tick
        self.assertEqual(p.props["test_throttle"], 0.0)
        self.assertEqual(p.props["test_brake"], 1.0)


class CameraClearance(unittest.TestCase):
    """v9 review: ped and STOP-corner cameras ended up inside poles and walls; the UE scripts probe from open air
    and pull the camera in front of the first hit (clear_camera), or skip the view."""

    def test_clear_line_keeps_the_camera(self):
        spot, moved = P.clear_camera((0, 0, 170), (800, 0, 170), None)
        self.assertEqual(spot, (800, 0, 170))
        self.assertEqual(moved, 0.0)
        spot, moved = P.clear_camera((0, 0, 170), (800, 0, 170), 9.0)      # the hit lies past the camera
        self.assertEqual(spot, (800, 0, 170))

    def test_pole_between_pulls_the_camera_in_front_of_it(self):
        spot, moved = P.clear_camera((0, 0, 170), (800, 600, 170), 7.0)    # 10 m line, a pole at 7 m
        self.assertAlmostEqual(math.hypot(spot[0], spot[1]) / 100.0, 7.0 - P.CAM_CLEAR_M, 6)
        self.assertAlmostEqual(spot[1] / spot[0], 0.75, 6)                 # on the same line
        self.assertEqual(spot[2], 170)
        self.assertAlmostEqual(moved, 3.0 + P.CAM_CLEAR_M, 6)

    def test_too_close_is_skipped(self):
        spot, moved = P.clear_camera((0, 0, 170), (600, 0, 170), P.CAM_MIN_M)
        self.assertIsNone(spot)
        self.assertGreater(moved, 0.0)


if __name__ == "__main__":
    unittest.main()
