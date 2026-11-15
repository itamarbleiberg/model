"""Geometry of the Time Blade (shared by all five variants).

Model space: 1 unit = 1/16 block. The weapon stands upright, front (armour plates)
facing +Z (south), centred on x = 8, z = 8.

Parts
  * two long curved horn blades forming a "U" around the body, joined under it
  * armoured oval body made of overlapping chevron plates (shingled tiles)
  * three pointed crown plates on top (centre one larger, in front)
  * neck + oval grip cuff with flange and rim
  * rivets, inner core, back shell
  * crackling energy planes (animated lightning) hugging the blade edges
"""
import math
import numpy as np
from mc import Elem, unit, frame, rot_about, FACES

XC, ZC = 8.0, 8.0

# ---------------------------------------------------------------- body shape
Y_BOT = -1.55        # bottom tip of the armoured body
Y_TOP = 14.7         # rounded top of the body (behind the crown)
W_MAX = 5.15         # half width of the body
ZB = 5.85            # back plane of the body
D_FRONT = 4.75       # front dome height above the back plane
D_BACK = 1.05        # back shell bulge
RIDGE = 0.32         # extra height of the vertical centre ridge
SEAMS = [6.75, 3.55, 0.55]   # chevron seam heights on the centre line (top to bottom)
SEAM_RISE = 1.85     # how much a seam rises from the centre line to the body edge


def _mid_w(y):
    return W_MAX - 0.10 * ((y - 7.8) / 3.8) ** 2


def half_width(y):
    if y <= 4.1:
        wb = _mid_w(4.1)
        t = min(1.0, max(0.0, (4.1 - y) / (4.1 - Y_BOT)))
        return wb * max(0.0, 1 - t ** 2.15) ** (1 / 2.15)
    if y <= 11.4:
        return _mid_w(y)
    wt = _mid_w(11.4)
    t = min(1.0, max(0.0, (y - 11.4) / (Y_TOP - 11.4)))
    return wt * max(0.0, 1 - t ** 2.0) ** 0.5


def _profile(y):
    """Vertical bulge profile of the dome (side view)."""
    if y < 5.4:
        t = (5.4 - y) / (5.4 - Y_BOT + 0.35)
        return max(0.0, 1 - t * t) ** 0.5
    if y > 9.4:
        t = (y - 9.4) / (Y_TOP - 9.4 + 1.6)
        return max(0.0, 1 - t * t) ** 0.5
    return 1.0


def front_height(u, y):
    u = min(1.0, abs(u))
    lat = max(0.0, 1 - u ** 2.25) ** (1 / 2.25)
    ridge = RIDGE * max(0.0, 1 - u / 0.42) ** 1.3
    return (D_FRONT * lat + ridge) * _profile(y)


def back_height(u, y):
    u = min(1.0, abs(u))
    lat = max(0.0, 1 - u ** 2.0) ** 0.5
    return D_BACK * lat * (0.55 + 0.45 * _profile(y))


def body_point(u, y, back=False):
    w = half_width(y)
    x = XC + u * w
    z = ZB - back_height(u, y) if back else ZB + front_height(u, y)
    return np.array([x, y, z])


def body_normal(u, y, back=False, h=1e-3):
    """Outward normal of the body surface at (u, y)."""
    w = max(half_width(y), 0.2)
    du = h / w
    p = body_point(u, y, back)
    pu = body_point(min(1, u + du), y, back) - body_point(max(-1, u - du), y, back)
    py = body_point(u, y + h, back) - body_point(u, y - h, back)
    n = unit(np.cross(pu, py))
    if back:
        n = -n
    if n[2] * (-1 if back else 1) < -0.5:
        n = -n
    return n, p


def seam_y(k, u):
    return SEAMS[k] + SEAM_RISE * abs(u) ** 1.12


def body_uy(p):
    """Inverse of body_point for the front: returns (u, y)."""
    y = p[1]
    w = max(half_width(y), 1e-3)
    return (p[0] - XC) / w, y


# ---------------------------------------------------------------- helpers
_JIT = [0]


def fit_tile(c4, thick, out_hint, ov=(0.07, 0.07), lip=0.0, extra_up=0.0,
             extra_down=0.0, raise_=0.0):
    # tiny deterministic jitter so neighbouring tile sides are never exactly coplanar
    jx = jy = 0.0
    """Best fitting oriented box whose outer face spans the quad tl, tr, br, bl."""
    tl, tr, br, bl = [np.asarray(c, float) for c in c4]
    xdir = unit((tr - tl) + (br - bl))
    ydir = (tl - bl) + (tr - br)
    ydir = unit(ydir - xdir * np.dot(xdir, ydir))
    n = np.cross(xdir, ydir)
    if np.dot(n, out_hint) < 0:
        xdir = -xdir
        n = -n
    pts = np.stack([tl, tr, br, bl])
    c = pts.mean(axis=0)
    rel = pts - c
    px, py, pn = rel @ xdir, rel @ ydir, rel @ n
    w = px.max() - px.min() + 2 * ov[0]
    h = py.max() - py.min() + 2 * ov[1] + extra_up + extra_down
    cx = (px.max() + px.min()) / 2
    cy = (py.max() + py.min()) / 2 + (extra_up - extra_down) / 2
    top_n = 0.55 * pn.max() + 0.45 * pn.mean() + raise_
    R = np.stack([xdir, ydir, n], axis=1)
    center = c + xdir * (cx + jx) + ydir * (cy + jy) + n * (top_n - thick / 2)
    if lip > 0:
        th = math.atan2(lip, h)
        y2 = ydir * math.cos(th) - n * math.sin(th)
        n2 = n * math.cos(th) + ydir * math.sin(th)
        top = center + ydir * h / 2 + n * thick / 2
        center = top - y2 * h / 2 - n2 * thick / 2
        R = np.stack([xdir, y2, n2], axis=1)
    return center, R, (w, h, thick)


class Builder:
    def __init__(self):
        self.elems = []

    def add(self, center, R, size, **kw):
        e = Elem(center, R, size, **kw)
        self.elems.append(e)
        return e


# ---------------------------------------------------------------- blades
# The right half of the "U" is generated from a monotonic curvature profile so the
# horn never S-bends: heading east under the body, sweeping up the side and
# leaning inwards towards the tip. The left half is its mirror image.
U_Y0 = -2.15         # height of the centre line under the body
U_TURN = 11.6        # arc length of the bottom quarter turn
U_UP = 19.9          # arc length of the upright part
U_TIP_ANGLE = 114.0  # heading at the tip (90 = straight up)
# (arc fraction, radial thickness, depth along z)
T_PROFILE = [(0.0, 1.42), (0.22, 1.55), (0.42, 1.72), (0.62, 1.64), (0.78, 1.34),
             (0.90, 0.90), (0.97, 0.46), (1.0, 0.24)]
D_PROFILE = [(0.0, 2.5), (0.25, 2.8), (0.5, 2.85), (0.7, 2.5), (0.85, 1.9),
             (0.95, 1.15), (1.0, 0.64)]
T_REF = 1.72         # thickness used for the inner edge line (outer edge tapers -> horn tip)
ENERGY_MARGIN = 1.0


def _centerline(n=1400):
    S = U_TURN + U_UP
    ss = np.linspace(0, S, n)
    t = np.clip(ss / U_TURN, 0, 1)
    turn = 90.0 * (3 * t ** 2 - 2 * t ** 3)
    up = np.clip((ss - U_TURN) / U_UP, 0, 1)
    th = np.radians(np.where(ss < U_TURN, turn, 90.0 + (U_TIP_ANGLE - 90.0) * up ** 1.6))
    dx, dy = np.cos(th), np.sin(th)
    ds = np.diff(ss)
    x = XC + np.concatenate([[0], np.cumsum((dx[1:] + dx[:-1]) / 2 * ds)])
    y = U_Y0 + np.concatenate([[0], np.cumsum((dy[1:] + dy[:-1]) / 2 * ds)])
    return np.stack([x, y], axis=1), ss


class BladeCurve:
    def __init__(self):
        pts, ss = _centerline()
        self.s = ss
        self.pts = pts
        self.S = self.s[-1]

    def at(self, s):
        """Centre line point for signed arc length s (negative = left half)."""
        a = abs(s)
        x = np.interp(a, self.s, self.pts[:, 0])
        y = np.interp(a, self.s, self.pts[:, 1])
        if s < 0:
            x = 2 * XC - x
        return np.array([x, y])

    def tangent(self, s, h=0.05):
        return unit(self.at(s + h) - self.at(s - h))

    def thickness(self, s):
        f = min(1.0, abs(s) / self.S)
        return float(np.interp(f, *zip(*T_PROFILE)))

    def depth(self, s):
        f = min(1.0, abs(s) / self.S)
        return float(np.interp(f, *zip(*D_PROFILE)))

    def thickness_v(self, s):
        f = np.minimum(1.0, np.abs(s) / self.S)
        return np.interp(f, *zip(*T_PROFILE))

    def depth_v(self, s):
        f = np.minimum(1.0, np.abs(s) / self.S)
        return np.interp(f, *zip(*D_PROFILE))

    def polyline3d(self, step=0.25):
        ss = np.arange(-self.S, self.S + 1e-6, step)
        return np.array([[*self.at(s), ZC] for s in ss]), ss


def blade_cuts(S):
    """Segment boundaries along the right half (arc length)."""
    cuts = [0.95]
    s = 0.95
    while s < S - 0.05:
        if s < 9.5:
            d = 1.05
        elif s < 21.5:
            d = 1.55
        elif s < S - 3.2:
            d = 1.25
        else:
            d = 0.8
        s = min(S, s + d)
        if S - s < 0.35:
            s = S
        cuts.append(s)
    return cuts


def build_blades(B, curve):
    cuts = blade_cuts(curve.S)
    bounds = [-c for c in reversed(cuts)] + cuts      # left tip ... right tip
    segs = list(zip(bounds[:-1], bounds[1:]))
    zaxis = np.array([0.0, 0.0, 1.0])
    for i, (sa, sb) in enumerate(segs):
        A, Bp = curve.at(sa), curve.at(sb)
        Tn = unit(Bp - A)
        nrm = np.array([Tn[1], -Tn[0]])               # outward (away from the U interior)
        sm = (sa + sb) / 2
        t = curve.thickness(sm)
        d = curve.depth(sm)
        # neighbouring directions -> joint extension so the outer side has no wedge gap
        ext = []
        for s_join, other in ((sa, sa - 0.4), (sb, sb + 0.4)):
            if abs(other) > curve.S:
                ext.append(0.0)
                continue
            ang = math.acos(max(-1, min(1, float(np.dot(curve.tangent(s_join - 0.3), curve.tangent(s_join + 0.3))))))
            ext.append(t / 2 * math.tan(ang / 2) + 0.04)
        L = float(np.linalg.norm(Bp - A))
        if abs(sa) >= curve.S - 1e-6:
            ext[0] = 0.0
        if abs(sb) >= curve.S - 1e-6:
            ext[1] = 0.0
        alt = 0.014 if i % 2 else -0.014
        tt = t + alt
        offset = (tt - T_REF) / 2 if abs(sm) > 2.0 else 0.0   # keep the inner edge, taper the outer edge
        mid = (A + Bp) / 2 + Tn * (ext[1] - ext[0]) / 2 + nrm * offset
        R = np.stack([np.array([nrm[0], nrm[1], 0.0]), np.array([Tn[0], Tn[1], 0.0]), zaxis], axis=1)
        Lx = L + ext[0] + ext[1]
        c3 = np.array([mid[0], mid[1], ZC])
        meta = dict(kind="blade", s_center=float((sa + sb) / 2 + (ext[1] - ext[0]) / 2),
                    t=tt, d=d + alt, seg=i, nseg=len(segs))
        side = "L" if sm < -1 else ("R" if sm > 1 else "C")
        core_d = (d + alt) * 0.76
        B.add(c3, R, (tt, Lx, core_d), tex="blade", mat=dict(meta, part="core"),
              name=f"blade_{side}{i:02d}_core", light=15)
        fin_t = max(0.12, tt * 0.46)
        fin_d = (d + alt) * 0.12
        for sgn in (1, -1):
            fz = sgn * (core_d / 2 + fin_d / 2 - 0.004)
            B.add(c3 + zaxis * fz + np.array([nrm[0], nrm[1], 0]) * (tt * 0.12),
                  R, (fin_t, Lx - 0.02, fin_d), tex="blade",
                  mat=dict(meta, part="fin", fin=sgn), name=f"blade_{side}{i:02d}_fin{'F' if sgn > 0 else 'B'}",
                  light=15)
        # energy planes (zero thickness, both faces share one texture region)
        m = ENERGY_MARGIN
        e1 = B.add(c3, R, (tt + 2 * m, Lx, 0.0), tex="energy", faces=("north", "south"),
                   mat=dict(meta, kind="energy", orient="front"), name=f"spark_{side}{i:02d}_a",
                   light=15, plane=2)
        e1.share = {"north": "south"}
        e2 = B.add(c3, R, (0.0, Lx, (d + alt) + 2 * m), tex="energy", faces=("west", "east"),
                   mat=dict(meta, kind="energy", orient="side"), name=f"spark_{side}{i:02d}_b",
                   light=15, plane=0)
        e2.share = {"west": "east"}
    return segs


# ---------------------------------------------------------------- body
def _band_rows(k):
    """(bottom boundary fn, top boundary fn, rows) for band k (0 = top band A)."""
    if k == 0:
        return (lambda u: seam_y(0, u)), (lambda u: 13.05 - 0.15 * abs(u)), 4
    if k in (1, 2):
        return (lambda u, k=k: seam_y(k, u)), (lambda u, k=k: seam_y(k - 1, u)), 2
    return None


COLS = [0.0, 0.2, 0.4, 0.59, 0.76, 0.9, 1.0]


def build_body(B):
    out = []
    # ---- chevron bands A, B, C (rows of shingled tiles) -------------------
    for k in range(3):
        bot, top, rows = _band_rows(k)
        for sgn in (1, -1):
            for j in range(len(COLS) - 1):
                ua, ub = COLS[j], COLS[j + 1]
                for r in range(rows):
                    fa, fb = r / rows, (r + 1) / rows

                    def Y(u, f):
                        return bot(u) + f * (top(u) - bot(u))
                    tl = body_point(sgn * ua, Y(ua, fb))
                    tr = body_point(sgn * ub, Y(ub, fb))
                    br = body_point(sgn * ub, Y(ub, fa))
                    bl = body_point(sgn * ua, Y(ua, fa))
                    um = (ua + ub) / 2
                    nh, _ = body_normal(sgn * um, Y(um, (fa + fb) / 2))
                    lip = 0.24 if r == 0 else 0.0
                    up = 0.45 if r == rows - 1 and k > 0 else 0.12
                    c, R, size = fit_tile((tl, tr, br, bl), 0.62, nh, ov=(0.08 + 0.013 * (r % 2), 0.06 + 0.013 * (j % 2)),
                                          lip=lip, extra_up=up, raise_=0.02 * r)
                    out.append(B.add(c, R, size, tex="body",
                                     mat=dict(kind="plate", band=k, row=r, col=j, half=sgn),
                                     name=f"plate_{'ABC'[k]}{r}{j}{'R' if sgn > 0 else 'L'}"))
    # ---- bottom band D: horizontal rows tucked under band C ------------------
    rows_d = [-1.42, -0.72, 0.05, 0.85, 1.65, 2.55]
    for r in range(len(rows_d) - 1):
        ya, yb = rows_d[r], rows_d[r + 1]
        for sgn in (1, -1):
            for j in range(len(COLS) - 1):
                ua, ub = COLS[j], COLS[j + 1]
                if ya > seam_y(2, ub) + 0.05:
                    continue                      # completely under band C
                tl = body_point(sgn * ua, yb); tr = body_point(sgn * ub, yb)
                br = body_point(sgn * ub, ya); bl = body_point(sgn * ua, ya)
                nh, _ = body_normal(sgn * (ua + ub) / 2, (ya + yb) / 2)
                c, R, size = fit_tile((tl, tr, br, bl), 0.6, nh, ov=(0.08 + 0.013 * (r % 2), 0.07 + 0.013 * (j % 2)), extra_up=0.3,
                                      raise_=-0.11 + 0.028 * r)
                out.append(B.add(c, R, size, tex="body", mat=dict(kind="plate", band=3, row=r, col=j, half=sgn),
                                 name=f"plate_D{r}{j}{'R' if sgn > 0 else 'L'}"))
    # underside of the tip
    w0 = half_width(-1.42)
    B.add(np.array([XC, -1.52, ZB + front_height(0, -1.45) / 2 - 0.1]), None,
          (2 * w0 * 0.9, 0.3, front_height(0, -1.45) + 0.4), tex="body",
          mat=dict(kind="plate", band=3, row=-1, col=0, half=1), name="plate_tip")
    # ---- top cap (behind the crown) --------------------------------------
    for ci, (ya, yb, cols) in enumerate(((12.95, 13.95, [0.0, 0.36, 0.7, 1.0]), (13.9, Y_TOP - 0.02, [0.0, 0.5, 1.0]))):
        for sgn in (1, -1):
            for j in range(len(cols) - 1):
                ua, ub = cols[j], cols[j + 1]
                tl = body_point(sgn * ua, yb); tr = body_point(sgn * ub, yb)
                br = body_point(sgn * ub, ya); bl = body_point(sgn * ua, ya)
                nh, _ = body_normal(sgn * (ua + ub) / 2, (ya + yb) / 2)
                c, R, size = fit_tile((tl, tr, br, bl), 0.6, nh, ov=(0.1 + 0.013 * (ci % 2), 0.1 + 0.013 * (j % 2)), raise_=-0.06 + 0.035 * ci)
                B.add(c, R, size, tex="body", mat=dict(kind="plate", band=0, row=9, col=j, half=sgn),
                      name=f"plate_top{j}{'R' if sgn > 0 else 'L'}")
    # ---- back shell --------------------------------------------------------
    rows_y = [Y_BOT + 0.05, 0.4, 2.2, 4.4, 6.8, 9.2, 11.4, 13.1, 14.2, Y_TOP - 0.05]
    bcols = [0.0, 0.34, 0.66, 0.88, 1.0]
    for i in range(len(rows_y) - 1):
        ya, yb = rows_y[i], rows_y[i + 1]
        for sgn in (1, -1):
            for j in range(len(bcols) - 1):
                ua, ub = bcols[j], bcols[j + 1]
                tl = body_point(sgn * ua, yb, back=True); tr = body_point(sgn * ub, yb, back=True)
                br = body_point(sgn * ub, ya, back=True); bl = body_point(sgn * ua, ya, back=True)
                nh, _ = body_normal(sgn * (ua + ub) / 2, (ya + yb) / 2, back=True)
                c, R, size = fit_tile((tl, tr, br, bl), 0.55, nh, ov=(0.07 + 0.013 * (i % 2), 0.07 + 0.013 * (j % 2)))
                B.add(c, R, size, tex="body", mat=dict(kind="back", row=i, col=j, half=sgn),
                      name=f"back_{i}{j}{'R' if sgn > 0 else 'L'}")
    # ---- dark inner core ---------------------------------------------------
    ys = np.arange(Y_BOT + 0.35, Y_TOP - 0.3, 0.9)
    for y in ys:
        yc = y + 0.45
        for lvl, a in enumerate((0.42, 0.7, 0.88)):
            w = min(half_width(y), half_width(y + 0.9)) * a
            if w < 0.5:
                continue
            front = min(front_height(a, y), front_height(a, y + 0.9)) - 0.72
            back = min(back_height(a, y), back_height(a, y + 0.9)) - 0.62
            if front + back < 0.3:
                continue
            c = np.array([XC, yc, ZB + (front - back) / 2])
            B.add(c, None, (2 * w, 0.9 - 0.035 * lvl - 0.012 * (int(round(y * 10)) % 2), front + back),
                  tex="body", mat=dict(kind="core"), name="core")
    return out


def rivet_positions():
    pos = []
    for k, (u_list, dy) in enumerate([([-0.1, 0.1, -0.64, 0.64], 0.55),
                                      ([-0.1, 0.1, -0.62, 0.62], 0.52),
                                      ([-0.1, 0.1, -0.6, 0.6], 0.5)]):
        for u in u_list:
            pos.append((u, seam_y(k, u) + dy if k > 0 else seam_y(0, u) + dy))
    # band A extra pair under the crown edges, band D pair
    pos += [(-0.36, seam_y(0, 0.36) + 1.65), (0.36, seam_y(0, 0.36) + 1.65)]
    pos += [(-0.32, seam_y(2, 0.32) - 1.05), (0.32, seam_y(2, 0.32) - 1.05)]
    return pos


def build_rivets(B):
    for i, (u, y) in enumerate(rivet_positions()):
        n, p = body_normal(u, y)
        R = frame(np.cross([0, 1, 0], n) if abs(n[1]) < 0.9 else [1, 0, 0], [0, 1, 0])
        # make local z the normal
        x = unit(np.cross([0, 1, 0], n))
        y_ = np.cross(n, x)
        R = np.stack([x, y_, n], axis=1)
        B.add(p + n * 0.14, R, (0.5, 0.5, 0.36), tex="body", mat=dict(kind="rivet"),
              name=f"rivet_{i:02d}")


# ---------------------------------------------------------------- crown
CROWN = [
    # name, centre(x,y), z offset in front of body, yaw, pitch, hw, apex, shoulder, lower, bottom, thick, ridge yaw
    ("C", (XC, 12.45), 0.42, 0.0, -13.0, 2.32, 3.3, 1.25, -1.55, -3.1, 1.15, 21.0),
    ("L", (XC - 3.72, 12.05), 0.18, -33.0, -10.0, 1.78, 2.4, 0.85, -1.2, -2.3, 0.95, 19.0),
    ("R", (XC + 3.72, 12.05), 0.18, 33.0, -10.0, 1.78, 2.4, 0.85, -1.2, -2.3, 0.95, 19.0),
]


def crown_frames():
    out = {}
    for (nm, (cx, cy), zoff, yaw, pitch, hw, ya, ys, yl, yb, th, ry) in CROWN:
        u, _ = body_uy(np.array([cx, cy, 0]))
        z = ZB + front_height(u, cy) + zoff
        base = rot_about([0, 1, 0], yaw) @ rot_about([1, 0, 0], pitch)
        out[nm] = (np.array([cx, cy, z]), base)
    return out


def _plane_tile(B, origin, hx, hy, hz, p_a, p_b, height, side, thick, recess, mat, name):
    """Box lying in the plane (hx, hy) whose long edge runs from p_a to p_b (2D plane coords).

    The box extends `height` to one side of that edge ('below' or 'above')."""
    pa = origin + hx * p_a[0] + hy * p_a[1]
    pb = origin + hx * p_b[0] + hy * p_b[1]
    lx = unit(pb - pa)
    lz = hz
    ly = np.cross(lz, lx)
    want_up = side == "above"
    toward = ly if (np.dot(ly, hy) > 0) == want_up else -ly
    L = float(np.linalg.norm(pb - pa))
    c = (pa + pb) / 2 + toward * (height / 2) - hz * (thick / 2 + recess)
    R = np.stack([lx, ly, lz], axis=1)
    return B.add(c, R, (L, height, thick), tex="body", mat=mat, name=name)


def build_crown(B):
    frames = crown_frames()
    for (nm, (cx, cy), zoff, yaw, pitch, hw, ya, ys, yl, yb, th, ry) in CROWN:
        c0, base = frames[nm]
        X, Y, Z = base[:, 0], base[:, 1], base[:, 2]
        k_top = (ya - ys) / hw          # slope of the upper edges
        k_bot = (yl - yb) / hw          # slope of the lower edges
        sw = 0.52                       # raised centre spine
        # spine (ridge) with pointed caps
        sp_top, sp_bot = ya - 0.55, yb + 0.5
        B.add(c0 + Y * ((sp_top + sp_bot) / 2) - Z * ((th + 0.14) / 2 - 0.14), base,
              (sw, sp_top - sp_bot, th + 0.14), tex="body",
              mat=dict(kind="crown", piece=nm, part="spine", half=0), name=f"crown_{nm}_spine")
        dia = rot_about(Z, 45.0) @ base
        a = 0.56
        for yy, nmc in ((ya - a / math.sqrt(2), "tip"), (yb + a / math.sqrt(2), "foot")):
            B.add(c0 + Y * yy - Z * ((th + 0.1) / 2 - 0.12), dia, (a, a, th + 0.1), tex="body",
                  mat=dict(kind="crown", piece=nm, part="spine", half=0), name=f"crown_{nm}_{nmc}")
        for sgn in (1, -1):
            hf = rot_about(Y, -sgn * ry) @ base               # facet yawed back -> convex plate
            hx, hy, hz = hf[:, 0], hf[:, 1], hf[:, 2]
            o = c0 + X * (sgn * 0.2)                          # facet inner edge (under the spine)
            A = hw - 0.2
            tag = f"crown_{nm}_{'R' if sgn > 0 else 'L'}"
            mat = dict(kind="crown", piece=nm, half=sgn)
            # main slab between the shoulders and the lower corners
            B.add(o + hx * (sgn * (A + 0.04) / 2) + hy * ((ys + yl) / 2) - hz * (th / 2), hf,
                  (A + 0.04, ys - yl, th), tex="body", mat=dict(mat, part="main"), name=tag + "_main")
            # upper slope tile + stair under it
            y_in = ya - 0.3 * k_top
            _plane_tile(B, o, hx, hy, hz, (sgn * 0.08, y_in + 0.02 * k_top), (sgn * (A + 0.05), ys - 0.04 * k_top),
                        0.92, "below", th - 0.04, 0.025, dict(mat, part="roof"), tag + "_roof")
            st_w = min(A * 0.62, 1.15)
            st_h = (ya - ys) * 0.55
            B.add(o + hx * (sgn * (0.03 + st_w / 2)) + hy * (ys + st_h / 2 - 0.05) - hz * (th / 2 + 0.05), hf,
                  (st_w, st_h + 0.1, th - 0.16), tex="body", mat=dict(mat, part="stair"), name=tag + "_stair")
            # lower V tile + stair above it
            y_inb = yb + 0.3 * k_bot
            _plane_tile(B, o, hx, hy, hz, (sgn * 0.08, y_inb - 0.02 * k_bot), (sgn * (A + 0.05), yl + 0.04 * k_bot),
                        0.86, "above", th - 0.04, 0.025, dict(mat, part="vee"), tag + "_vee")
            sb_h = (yl - yb) * 0.5
            B.add(o + hx * (sgn * (0.03 + st_w / 2)) + hy * (yl - sb_h / 2 + 0.05) - hz * (th / 2 + 0.05), hf,
                  (st_w, sb_h + 0.1, th - 0.16), tex="body", mat=dict(mat, part="stair"), name=tag + "_stairb")
        # filler behind the piece (connects it to the body, hidden)
        fc = c0 - Z * (th + 0.55)
        B.add(fc, base, (hw * 1.45, (ys - yl) * 0.95, 1.3), tex="body", mat=dict(kind="core"),
              name=f"crown_{nm}_filler")


# ---------------------------------------------------------------- cuff / grip
CUFF = dict(rx=3.1, rz=2.3, y0=-6.55, y1=-2.95)


def _ellipse_ring(B, rx, rz, y0, y1, thick, n, kind, name, inner_dark=True, phase=0.0):
    angs = np.linspace(0, 2 * math.pi, n + 1) + phase
    for i in range(n):
        a0, a1 = angs[i], angs[i + 1]
        p0 = np.array([XC + rx * math.sin(a0), 0, ZC + rz * math.cos(a0)])
        p1 = np.array([XC + rx * math.sin(a1), 0, ZC + rz * math.cos(a1)])
        tdir = unit(p1 - p0)
        out = unit(np.cross(tdir, [0, 1, 0]))
        if np.dot(out, (p0 + p1) / 2 - np.array([XC, 0, ZC])) < 0:
            out = -out
        # frame: x = tangent, y = up, z = outward
        x = tdir
        if np.dot(np.cross(x, [0, 1, 0]), out) < 0:
            x = -x
        R = np.stack([x, np.array([0.0, 1.0, 0.0]), np.cross(x, [0, 1, 0])], axis=1)
        L = float(np.linalg.norm(p1 - p0)) + 0.12
        mid = (p0 + p1) / 2
        dy = 0.014 if i % 2 else 0.0
        dt = 0.014 if i % 2 else 0.0
        c = np.array([mid[0], (y0 + y1) / 2, mid[2]]) - out * ((thick - dt) / 2)
        B.add(c, R, (L, y1 - y0 - 2 * dy, thick - dt), tex="body",
              mat=dict(kind=kind, ang=float((a0 + a1) / 2), idx=i), name=f"{name}_{i:02d}")


def build_cuff(B):
    c = CUFF
    # neck between body and cuff (mostly hidden behind the blade band)
    B.add(np.array([XC, -2.42, ZC]), None, (3.3, 1.8, 1.9), tex="body", mat=dict(kind="neck"), name="neck")
    _ellipse_ring(B, c["rx"], c["rz"], c["y0"] + 0.45, c["y1"] - 0.55, 0.6, 18, "cuff", "cuff")
    # top flange and bottom rim
    _ellipse_ring(B, c["rx"] + 0.32, c["rz"] + 0.3, c["y1"] - 0.62, c["y1"], 0.7, 18, "flange", "flange",
                  phase=math.pi / 18)
    _ellipse_ring(B, c["rx"] + 0.26, c["rz"] + 0.24, c["y0"], c["y0"] + 0.5, 0.66, 18, "rim", "rim",
                  phase=math.pi / 18)
    # recessed dark bottom inside the cuff + a grip bar
    ri_x, ri_z = c["rx"] - 0.55, c["rz"] - 0.55
    for k, (fx, fz) in enumerate(((0.96, 0.42), (0.42, 0.96), (0.74, 0.74))):
        B.add(np.array([XC, c["y0"] + 1.2, ZC]), None, (2 * ri_x * fx, 0.4 - 0.03 * k, 2 * ri_z * fz), tex="body",
              mat=dict(kind="cuffinner"), name="cuff_inner")
    B.add(np.array([XC, c["y0"] + 0.85, ZC]), None, (2 * (ri_x + 0.25) * 0.97, 0.62, 0.86), tex="body",
          mat=dict(kind="grip"), name="cuff_grip")


# ---------------------------------------------------------------- assemble
def build():
    _JIT[0] = 0
    B = Builder()
    curve = BladeCurve()
    build_blades(B, curve)
    build_body(B)
    build_rivets(B)
    build_crown(B)
    build_cuff(B)
    return B.elems, curve
