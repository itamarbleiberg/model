"""Procedural pixel-art materials, baked per texel from the texel's 3D position.

Metal parts are painted with a limited palette + 4x4 ordered dithering, a baked key
light from the upper left, hammered cells, seams, bevel rims and rivet shadows.
Blades get layered gradients, energy veins, sparkles and a travelling energy wave.
Energy planes get jagged lightning bolts with soft glow pixels (animated).
"""
import math
import numpy as np
import design as D
from mc import unit

LB = unit([-0.45, 0.68, 0.60])            # baked key light (upper left, front)
B4 = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16.0 - 0.5


# ---------------------------------------------------------------- noise utils
def _hash(*ints):
    h = np.uint64(0x9E3779B97F4A7C15)
    acc = np.zeros(np.broadcast(*ints).shape, dtype=np.uint64) + h
    for v in ints:
        v = np.asarray(v).astype(np.int64).astype(np.uint64)
        acc ^= v + np.uint64(0x9E3779B97F4A7C15) + (acc << np.uint64(6)) + (acc >> np.uint64(2))
        acc *= np.uint64(0xBF58476D1CE4E5B9)
        acc ^= acc >> np.uint64(31)
    return acc


def rnd(*ints):
    return (_hash(*ints) >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def voronoi(x, y, cell, seed):
    gx = np.floor(x / cell).astype(np.int64)
    gy = np.floor(y / cell).astype(np.int64)
    d1 = np.full(x.shape, 1e9); d2 = np.full(x.shape, 1e9)
    cid = np.zeros(x.shape, dtype=np.int64)
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            cx, cy = gx + ox, gy + oy
            px = (cx + 0.15 + 0.7 * rnd(cx, cy, seed)) * cell
            py = (cy + 0.15 + 0.7 * rnd(cx, cy, seed + 1)) * cell
            d = np.hypot(x - px, y - py)
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            cid = np.where(closer, cx * 7919 + cy * 104729, cid)
            d1 = np.where(closer, d, d1)
    return d1, d2, cid


def ramp(t, pal, i, j, dither=0.55):
    pal = np.asarray(pal, np.float32)
    n = len(pal)
    x = np.clip(t, 0, 1) * (n - 1)
    d = B4[j % 4, i % 4] * dither
    idx = np.clip(np.floor(x + 0.5 + d), 0, n - 1).astype(int)
    return pal[idx]


def texel_ij(S, T, w, h):
    i = np.floor(S * w).astype(int) % 4096
    j = np.floor(T * h).astype(int) % 4096
    return i, j


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy + 1e-12
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / L2, 0, 1)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy)), t


# ---------------------------------------------------------------- body shape (vectorised)
def v_half_width(y):
    y = np.asarray(y, float)
    wb = D._mid_w(4.1)
    tl = np.clip((4.1 - y) / (4.1 - D.Y_BOT), 0, 1)
    lo = wb * np.maximum(0, 1 - tl ** 2.15) ** (1 / 2.15)
    mid = D.W_MAX - 0.10 * ((y - 7.8) / 3.8) ** 2
    wt = D._mid_w(11.4)
    th = np.clip((y - 11.4) / (D.Y_TOP - 11.4), 0, 1)
    hi = wt * np.maximum(0, 1 - th ** 2) ** 0.5
    return np.where(y <= 4.1, lo, np.where(y <= 11.4, mid, hi))


def v_profile(y):
    y = np.asarray(y, float)
    tl = (5.4 - y) / (5.4 - D.Y_BOT + 0.35)
    th = (y - 9.4) / (D.Y_TOP - 9.4 + 1.6)
    lo = np.maximum(0, 1 - tl * tl) ** 0.5
    hi = np.maximum(0, 1 - th * th) ** 0.5
    return np.where(y < 5.4, lo, np.where(y > 9.4, hi, 1.0))


def v_front_height(u, y):
    u = np.minimum(1.0, np.abs(u))
    lat = np.maximum(0, 1 - u ** 2.25) ** (1 / 2.25)
    ridge = D.RIDGE * np.maximum(0, 1 - u / 0.42) ** 1.3
    return (D.D_FRONT * lat + ridge) * v_profile(y)


def v_body_normal(u, y):
    """Smooth analytic normal of the front dome (ignores the faceting of the tiles)."""
    w = np.maximum(v_half_width(y), 0.3)
    eps = 0.02
    u = np.clip(u, -0.995, 0.995)
    zx = (v_front_height(u + eps / w, y) - v_front_height(u - eps / w, y)) / (2 * eps)
    zy = (v_front_height(u, y + eps) - v_front_height(u, y - eps)) / (2 * eps)
    # include the change of x with y (outline narrowing) only weakly
    n = np.stack([-zx, -zy, np.ones_like(zx)], axis=-1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def v_seam(k, u):
    return D.SEAMS[k] + D.SEAM_RISE * np.abs(u) ** 1.12


# ---------------------------------------------------------------- the material set
class Materials:
    def __init__(self, variant, curve):
        self.v = variant
        self.curve = curve
        poly, ss = curve.polyline3d(0.3)
        self.poly = poly
        self.rivets = []
        for (u, y) in D.rivet_positions():
            n, p = D.body_normal(u, y)
            self.rivets.append(p)
        self.rivets = np.array(self.rivets)
        self.crown = D.crown_frames()
        self.crown_dims = {c[0]: c for c in D.CROWN}
        self._bolts = {}

    # ------------------------------------------------------------- dispatcher
    def __call__(self, e, f, P, n, S, T, w, h, frame, nframes):
        kind = e.mat.get("kind")
        fn = getattr(self, "m_" + kind)
        out = fn(e, f, P, n, S, T, w, h, frame, nframes)
        return out

    # ------------------------------------------------------------- shared metal helpers
    def shade_metal(self, nrm, extra=0.0):
        d = np.clip(nrm @ LB, 0, 1)
        env = 0.5 + 0.5 * nrm[..., 1]
        return 0.16 + 0.50 * d + 0.20 * env + extra

    def glow_tint(self, P, nrm):
        g0 = self.v["body_glow"]
        if g0 <= 0:
            return None
        flat = P.reshape(-1, 3)
        d2 = ((flat[:, None, :] - self.poly[None, :, :]) ** 2).sum(-1)
        k = np.argmin(d2, axis=1)
        dist = np.sqrt(d2[np.arange(len(flat)), k]).reshape(P.shape[:2])
        vec = (self.poly[k] - flat).reshape(P.shape) / (dist[..., None] + 1e-6)
        if nrm.ndim == 1:
            facing = np.clip(vec @ nrm, 0, 1)
        else:
            facing = np.clip((vec * nrm).sum(-1), 0, 1)
        g = g0 * np.exp(-((dist - 0.6) / 2.1) ** 2) * (0.25 + 0.75 * facing)
        g = np.where(dist < 0.6, g0 * (0.25 + 0.75 * facing), g)
        return np.round(g * 6) / 6

    def finish(self, rgb, P, nrm, glow=True, alpha=1.0):
        out = np.ones(rgb.shape[:2] + (4,), np.float32)
        if glow:
            g = self.glow_tint(P, nrm)
            if g is not None:
                gc = np.array(self.v["glow"], np.float32)
                rgb = rgb + g[..., None] * gc * (1.0 - 0.55 * rgb)
        out[..., :3] = np.clip(rgb, 0, 1)
        out[..., 3] = alpha
        return out

    def hammered(self, a, b, cell, seed, amp):
        d1, d2, cid = voronoi(a, b, cell, seed)
        tone = (rnd(cid, seed + 7) - 0.5) * 2 * amp
        edge = (d2 - d1) < cell * 0.09
        return tone, edge

    def rivet_shadow(self, P):
        out = np.zeros(P.shape[:2])
        for r in self.rivets:
            d = np.hypot(P[..., 0] - (r[0] + 0.16), P[..., 1] - (r[1] - 0.2))
            out = np.maximum(out, np.where(d < 0.34, 1.0, 0.0) * (np.abs(P[..., 2] - r[2]) < 1.2))
        return out

    # ------------------------------------------------------------- armour plates
    def m_plate(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        x, y = P[..., 0], P[..., 1]
        wy = np.maximum(v_half_width(y), 0.25)
        u = np.clip((x - D.XC) / wy, -1, 1)
        k = e.mat["band"]
        pal = self.v["body"]
        if f != "south":
            # thickness / underside of the plates
            base = 0.17 + 0.22 * max(0.0, float(n @ LB))
            if f == "down":
                base = 0.08
            t = np.full(x.shape, base)
            t += 0.03 * (rnd(np.floor(x * 4), np.floor(y * 4), 11) - 0.5)
            return self.finish(ramp(t, pal, i, j), P, n)
        ns = v_body_normal(u, y)
        nm = ns * 0.7 + n * 0.3
        nm /= np.linalg.norm(nm, axis=-1, keepdims=True)
        t = self.shade_metal(nm)
        # band coordinates
        if k == 3:
            bot = np.full(x.shape, D.Y_BOT)
            top = v_seam(2, u)
        else:
            bot = v_seam(k, u)
            top = np.full(x.shape, 13.05) if k == 0 else v_seam(k - 1, u)
        dy_b = y - bot
        dy_t = top - y
        # shadow under the lip of the plate above
        if k != 0 or e.mat.get("row", 0) != 9:
            t -= 0.24 * np.exp(-np.maximum(dy_t, 0) / 0.42) * (k != 0)
        # bright bevelled lower rim of this plate
        if k != 3:
            t += np.where(dy_b < 0.27, 0.2, np.where(dy_b < 0.52, 0.07, 0.0))
        else:
            # bottom cap: rim follows the outline
            edge = 1.0 - np.abs(u)
            t -= 0.12 * np.clip((0.25 - (y - D.Y_BOT)) / 0.25, 0, 1)
        # engraved chevron line parallel to the seam
        if k in (0, 1, 2):
            gy = bot + (0.42 if k else 0.36) * (top - bot if k else 3.1)
            gd = y - gy
            groove = (np.abs(gd) < 0.13) & (np.abs(u) < 0.86) & (np.abs(u) > 0.09)
            t = np.where(groove, t - 0.17, t)
            t = np.where((gd < -0.13) & (gd > -0.38) & (np.abs(u) < 0.86) & (np.abs(u) > 0.09), t + 0.07, t)
        dx = x - D.XC
        if e.mat.get("row") == 9:
            tone, edge = self.hammered(x, y, 1.15, 31, 0.045)
            t = t - 0.08 + tone - 0.035 * edge
            return self.finish(ramp(t, pal, i, j), P, nm)
        # centre ridge seam
        t = np.where(np.abs(dx) < 0.13, t - 0.3, t)
        t = np.where((dx <= -0.13) & (dx > -0.42), t + 0.1, t)
        t = np.where((dx >= 0.13) & (dx < 0.38), t - 0.05, t)
        # left half is a bit lighter (light from the left)
        t += np.where(dx < 0, 0.03, -0.03)
        # hammered metal
        tone, edge = self.hammered(x, y, 1.15, 31 + k, 0.045)
        t += tone - 0.035 * edge
        # wear scratches
        sc = rnd(np.floor(x * 1.3), np.floor(y * 0.9), 77 + k)
        scratch = (sc > 0.86) & (np.abs(((x * 4).astype(int) - (y * 4).astype(int)) % 9) == 0)
        t = np.where(scratch & (np.abs(dx) > 0.5), t + 0.08, t)
        # rivet shadows
        t -= 0.17 * self.rivet_shadow(P)
        return self.finish(ramp(t, pal, i, j), P, nm)

    def m_back(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        x, y = P[..., 0], P[..., 1]
        pal = self.v["body"]
        if f != "south":
            t = np.full(x.shape, 0.2)
            return self.finish(ramp(t, pal, i, j), P, n)
        t = np.full(x.shape, 0.2 + 0.22 * max(0.0, float(n @ LB)) + 0.12 * (0.5 + 0.5 * n[1]))
        dx = x - D.XC
        tone, edge = self.hammered(x, y, 1.3, 51, 0.04)
        t += tone - 0.03 * edge
        # horizontal ribs between rows and the centre seam
        for yy in (2.2, 6.8, 11.4):
            t = np.where(np.abs(y - yy) < 0.13, t - 0.14, t)
            t = np.where((y - yy > 0.13) & (y - yy < 0.38), t + 0.06, t)
        t = np.where(np.abs(dx) < 0.13, t - 0.16, t)
        # engraved hourglass emblem (time!)
        cy = 8.9
        hx = 1.9
        hy = 2.1
        ax = np.abs(dx); ay = y - cy
        inside = (np.abs(ay) <= hy) & (ax <= hx * np.abs(ay) / hy)
        on_edge = inside & ((ax > hx * np.abs(ay) / hy - 0.32) | (np.abs(np.abs(ay) - hy) < 0.25))
        t = np.where(on_edge, t + 0.2, t)
        t = np.where(inside & ~on_edge, t - 0.06, t)
        sand = inside & (ay < -0.3) & (np.abs(ay) > 1.0) & ~on_edge
        t = np.where(sand, t + 0.1, t)
        frame_ring = (np.abs(np.abs(ay) - (hy + 0.38)) < 0.13) & (ax < hx + 0.5)
        t = np.where(frame_ring, t + 0.14, t)
        return self.finish(ramp(t, pal, i, j), P, n)

    def m_core(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        t = np.full(P.shape[:2], 0.04) + 0.03 * rnd(i, j, 3)
        return self.finish(ramp(t, self.v["body"], i, j, 0.3), P, n, glow=False)

    def m_neck(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        t = np.full(P.shape[:2], 0.14 + 0.2 * max(0.0, float(n @ LB)))
        t = np.where(np.abs(P[..., 1] + 1.4) < 0.15, t + 0.1, t)
        return self.finish(ramp(t, self.v["cuff"], i, j), P, n)

    def m_rivet(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        L = e.to_local(P) - (e.frm + e.to) / 2
        if f == "south":
            t = 0.62 - 0.45 * L[..., 0] + 0.45 * L[..., 1]
        else:
            t = np.full(P.shape[:2], 0.3 + 0.3 * max(0.0, float(n @ LB)))
        pal = self.v["crown"]
        return self.finish(ramp(t, pal, i, j, 0.2), P, n)

    # ------------------------------------------------------------- crown
    def m_crown(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        nm = e.mat["piece"]
        c0, base = self.crown[nm]
        (_, _, _, _, _, hw, ya, ys, yl, yb, th, ry) = self.crown_dims[nm]
        q = P - c0
        qx = q @ base[:, 0]
        qy = q @ base[:, 1]
        pal = self.v["crown"]
        part = e.mat.get("part")
        if f != "south":
            t = 0.2 + 0.25 * max(0.0, float(n @ LB))
            t = np.full(qx.shape, t)
            if f == "down":
                t -= 0.08
            return self.finish(ramp(t, pal, i, j), P, n)
        # kite polygon distance (positive inside)
        ax = np.abs(qx)
        d_top = ((ya - qy) - ax * (ya - ys) / hw) / math.hypot(1, (ya - ys) / hw)
        d_side = hw - ax
        d_bot = ((qy - yb) - ax * (yl - yb) / hw) / math.hypot(1, (yl - yb) / hw)
        dist = np.minimum(np.minimum(d_top, d_side), d_bot)
        t = self.shade_metal(n[None, None, :] * np.ones(qx.shape + (1,)), -0.06)
        dome = 1 - np.clip(ax / hw, 0, 1) ** 2
        t += 0.1 * dome - 0.05 * np.clip((qy - yl) / (ya - yl), 0, 1) * (qx > 0)
        if part == "spine":
            t += 0.08
            t = np.where(qx < -0.12, t + 0.1, t)
        tone, edge = self.hammered(qx * 1.0, qy * 1.0, 0.82, 91 + ord(nm), 0.075)
        # hammered dimples catch light on their upper-left rim
        d1, d2, cid = voronoi(qx, qy, 0.82, 91 + ord(nm))
        t += tone - 0.05 * edge
        # outline + bevel
        t = np.where(dist < 0.27, t - 0.34, t)
        rim = (dist >= 0.27) & (dist < 0.55)
        upper_left = (qy > (ys + yl) / 2) | (qx < 0)
        t = np.where(rim & upper_left, t + 0.13, np.where(rim, t - 0.06, t))
        return self.finish(ramp(t, pal, i, j), P, n)

    # ------------------------------------------------------------- cuff / grip
    def _ring_shade(self, e, P, n):
        return 0.16 + 0.5 * max(0.0, float(n @ LB)) + 0.16 * (0.5 + 0.5 * n[1])

    def m_cuff(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        pal = self.v["cuff"]
        y = P[..., 1]
        if f != "south":
            t = np.full(y.shape, 0.07 if f == "north" else 0.2)
            return self.finish(ramp(t, pal, i, j), P, n, glow=f != "north")
        t = np.full(y.shape, self._ring_shade(e, P, n))
        ang = e.mat["ang"]
        # vertical slits at +-40 degrees and engraved middle band
        for a0 in (-0.72, 0.72, math.pi - 0.72, math.pi + 0.72):
            dd = abs(math.atan2(math.sin(ang - a0), math.cos(ang - a0)))
            if dd < 0.2:
                t = t - 0.22
        t = np.where(np.abs(y + 4.75) < 0.14, t - 0.2, t)
        t = np.where((y + 4.75 < -0.14) & (y + 4.75 > -0.4), t + 0.08, t)
        tone, edge = self.hammered(np.full(y.shape, ang * 3.0) + S * 0.8, y, 1.2, 61, 0.04)
        t += tone
        # darker towards the bottom (held in the hand)
        t -= 0.06 * np.clip((-4.9 - y) / 1.5, 0, 1)
        return self.finish(ramp(t, pal, i, j), P, n)

    def m_flange(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        pal = self.v["cuff"]
        y = P[..., 1]
        if f == "south":
            t = np.full(y.shape, self._ring_shade(e, P, n) + 0.1)
            top = D.CUFF["y1"]
            t = np.where(top - y < 0.25, t + 0.14, t)
            t = np.where(y - (top - 0.62) < 0.2, t - 0.12, t)
        elif f == "up":
            t = np.full(y.shape, 0.55)
        else:
            t = np.full(y.shape, 0.1 if f in ("north", "down") else 0.25)
        return self.finish(ramp(t, pal, i, j), P, n)

    def m_rim(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        pal = self.v["cuff"]
        y = P[..., 1]
        if f == "south":
            t = np.full(y.shape, self._ring_shade(e, P, n) + 0.05)
            t = np.where(y - D.CUFF["y0"] > 0.36, t + 0.12, t)
        elif f == "down":
            t = np.full(y.shape, 0.3)
        else:
            t = np.full(y.shape, 0.12)
        return self.finish(ramp(t, pal, i, j), P, n)

    def m_cuffinner(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        t = np.full(P.shape[:2], 0.06)
        return self.finish(ramp(t, self.v["cuff"], i, j, 0.2), P, n, glow=False)

    def m_grip(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        x = P[..., 0]
        wrap = ((np.floor((x - P[..., 1] * 0.6) * 4).astype(int)) % 3) == 0
        t = np.where(wrap, 0.1, 0.2)
        pal = [(0.10, 0.06, 0.04), (0.17, 0.10, 0.06), (0.24, 0.15, 0.09), (0.31, 0.2, 0.12)]
        return self.finish(ramp(t * 2, pal, i, j, 0.2), P, n, glow=False)

    # ------------------------------------------------------------- blades
    def _blade_coords(self, e, P):
        L = e.to_local(P) - (e.frm + e.to) / 2
        s = e.mat["s_center"] + L[..., 1]
        qr = L[..., 0]
        if e.mat.get("part") == "fin":
            qr = qr + 0.12 * e.mat["t"]
        qz = P[..., 2] - D.ZC
        return s, qr, qz

    def _wave(self, a, frame, nframes):
        v = self.v
        tt = frame / max(1, nframes)
        if v["flow"] == 0:
            # Pause: one heartbeat over the first frames, then nothing
            beat = max(0.0, 1 - abs(frame - 3) / 3.0) if frame < 7 else 0.0
            return np.full(a.shape, beat) * 0.9
        lam = 7.5
        ph = a / lam - v["flow"] * tt
        return np.maximum(0, np.cos(2 * math.pi * ph)) ** 6

    def m_blade(self, e, f, P, n, S, T, w, h, frame, nframes):
        i, j = texel_ij(S, T, w, h)
        v = self.v
        s, qr, qz = self._blade_coords(e, P)
        a = np.abs(s)
        Sx = self.curve.S
        part = e.mat.get("part")
        t_core = e.mat["t"]
        d_core = e.mat["d"] * 0.76
        qzn = np.clip(qz / (d_core / 2 + 1e-6), -1.3, 1.3)
        lit = float(n @ LB)
        metal = v["metal_blade"]
        if part == "core":
            if f == "east":       # outer broad face
                if metal:
                    band = np.exp(-((qzn - 0.25) / 0.38) ** 2)
                    I = 0.36 + 0.42 * band - 0.1 * np.clip(np.abs(qzn) - 0.75, 0, 1) * 4
                else:
                    aq = np.abs(qzn)
                    I = np.where(aq < 0.3, 0.5, np.where(aq < 0.72, 0.42, 0.33))
                    I = np.where(aq > 0.93, 0.52, I)
                    I = np.where(np.abs(qz) < 0.13, 0.6, I)
            elif f == "west":     # inner broad face
                if metal:
                    I = 0.28 + 0.3 * np.exp(-((qzn + 0.1) / 0.45) ** 2)
                else:
                    aq = np.abs(qzn)
                    I = np.where(aq < 0.4, 0.38, np.where(aq < 0.8, 0.32, 0.26))
                    I = np.where(aq > 0.93, 0.42, I)
            elif f in ("south", "north"):
                qrn = np.abs(qr) / (t_core / 2 + 1e-6)
                I = (0.5 if f == "south" else 0.4) + 0.12 * (qrn > 0.7)
            else:
                I = np.full(a.shape, 0.5)
        else:                     # fins (sharpened front / back edges)
            if f in ("south", "north"):
                I = np.full(a.shape, 0.7 if f == "south" else 0.6)
            else:
                I = np.full(a.shape, 0.56)
        if metal:
            I = I - 0.04
        I = I + 0.08 * lit
        if metal:
            # brushed steel streaks along the blade + clock-tick etchings near the hilt
            streak = rnd(np.floor(qz * 4 + 50), np.floor(a / 2.5), 5) - 0.5
            I = I + 0.05 * streak
            if part == "core" and f == "east":
                tick = (np.abs(((a - 1.0) % 1.6) - 0.8) > 0.68) & (a < 10.5) & (np.abs(qzn) < 0.45)
                I = np.where(tick, I - 0.22, I)
            # a faint warm sheen from the golden energy
            I = I + 0.06 * self._wave(a, frame, nframes)
        else:
            # energy veins running along the blade
            for kk, (amp, freq, ph, wd) in enumerate(((0.5, 0.29, 0.0, 0.11),)):
                jag = 0.12 * (rnd(np.floor(a / 0.5), kk, 13) - 0.5)
                vz = amp * np.sin(a * freq + ph + (s < 0) * 1.3) + jag
                if f in ("east", "west"):
                    vein = np.abs(qzn - vz) < (wd / (d_core / 2))
                    I = np.where(vein & ((np.floor(a * 1.7 + kk) % 7) != 0), np.maximum(I + 0.22, 0.7), I)
            I = I + 0.2 * self._wave(a, frame, nframes)
            # flecks of light (twinkle every frame)
            key = np.floor(P * 4).astype(np.int64)
            fseed = 0 if v["flow"] == 0 else frame      # Pause: sparkles are frozen in time too
            fl = rnd(key[..., 0], key[..., 1] * 3 + key[..., 2] * 7, fseed * 17 + 3)
            I = np.where(fl < 0.009, 0.95, np.where(fl < 0.026, I + 0.12, I))
            # brighter, hotter tips
            I = I + 0.14 * np.clip((a - (Sx - 3.5)) / 3.5, 0, 1)
        rgb = ramp(I, v["blade"], i, j, 0.22)
        if metal:
            key = np.floor(P * 4).astype(np.int64)
            fl = rnd(key[..., 0], key[..., 1] * 3 + key[..., 2] * 7, frame * 17 + 3)
            mote = fl < 0.012
            rgb = np.where(mote[..., None], np.array(v["spark_glow"], np.float32), rgb)
        out = np.ones(rgb.shape[:2] + (4,), np.float32)
        out[..., :3] = rgb
        return out

    # ------------------------------------------------------------- lightning
    def _bolt_set(self, orient, frame, nframes):
        key = (orient, frame)
        if key in self._bolts:
            return self._bolts[key]
        v = self.v
        S = self.curve.S
        rng = np.random.default_rng(1000 + frame * 37 + (0 if orient == "front" else 5000))
        bolts = []
        for side in (1, -1):
            for b in range(2):
                # jagged polyline: vertices every 0.4-0.8 units, close to the edge with sharp spikes
                ss = [-S - 1.0]
                while ss[-1] < S + 1.0:
                    ss.append(ss[-1] + rng.uniform(0.28, 0.62))
                ss = np.array(ss)
                zig = np.where(np.arange(len(ss)) % 2 == 0, 1.0, -1.0) * rng.uniform(0.06, 0.2, len(ss))
                drift = np.convolve(rng.normal(0, 0.12, len(ss)), np.ones(7) / 7, mode="same")
                off = (0.24 + 0.24 * b) + zig + drift
                spikes = rng.random(len(ss)) < (0.08 if b == 0 else 0.05)
                off = off + spikes * rng.uniform(0.3, 0.6, len(ss))
                off = np.clip(off, 0.08, 0.95)
                on = np.zeros(len(ss), bool)
                pos = -S - rng.uniform(0, 3)
                dens = v["bolt_density"] * (1.0 if b == 0 else 0.3)
                while pos < S:
                    ln = rng.uniform(4.0, 10.0) if b == 0 else rng.uniform(1.5, 4.0)
                    gap = rng.uniform(0.6, 2.6) / max(0.15, dens)
                    on |= (ss >= pos) & (ss < pos + ln)
                    pos += ln + gap
                bolts.append((side, ss, off, on))
        self._bolts[key] = bolts
        return bolts

    def m_energy(self, e, f, P, n, S, T, w, h, frame, nframes):
        v = self.v
        L = e.to_local(P) - (e.frm + e.to) / 2
        s = e.mat["s_center"] + L[..., 1]
        orient = e.mat["orient"]
        if orient == "front":
            q = L[..., 0]
            he = self.curve.thickness_v(s) / 2
        else:
            q = P[..., 2] - D.ZC
            he = self.curve.depth_v(s) / 2
        a = np.abs(s)
        core = np.zeros(q.shape, bool)
        glow = np.zeros(q.shape, bool)
        for (side, ss, off, on) in self._bolt_set(orient, frame, nframes):
            k = np.clip(np.searchsorted(ss, s) - 1, 0, len(ss) - 2)
            ob = np.interp(s, ss, off)
            onb = on[k] & on[k + 1]
            slope = (off[k + 1] - off[k]) / (ss[k + 1] - ss[k])
            qb = side * (he + ob)
            dperp = np.abs(q - qb) / np.sqrt(1 + slope ** 2)
            core |= onb & (dperp < 0.13)
            glow |= onb & (dperp < 0.29)
        out = np.zeros(q.shape + (4,), np.float32)
        cc = np.array(v["spark_core"], np.float32)
        gc = np.array(v["spark_glow"], np.float32)
        out[glow] = np.concatenate([gc, [0.42]])
        out[core] = np.concatenate([cc, [1.0]])
        # never draw inside the blade, fade out at the very tips
        out[np.abs(q) < he - 0.05] = 0
        fade = np.clip((self.curve.S + 0.2 - a) / 1.0, 0, 1)
        out[..., 3] *= fade
        return out
