"""Minecraft Java 1.21.11 block/item model math.

Everything here mirrors the game's own model baking so that the texture baker
and the preview renderer see exactly the geometry the game will build:

* element rotation uses the 1.21.11 multi-axis format: {"origin", "x", "y", "z"}
  baked by the game as Matrix4f.rotationZYX(z, y, x)  ->  M = Rz * Ry * Rx
* face vertex order and UV corner assignment follow FaceInfo / BlockElementFace
* quad lighting direction = closest axis direction of the rotated face normal
"""
import math
import numpy as np

FACES = ("down", "up", "north", "south", "west", "east")

# FaceInfo vertex order. 0 = min, 1 = max for (x, y, z).
FACE_CORNERS = {
    "down":  ((0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)),
    "up":    ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
    "north": ((1, 1, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0)),
    "south": ((0, 1, 1), (0, 0, 1), (1, 0, 1), (1, 1, 1)),
    "west":  ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)),
    "east":  ((1, 1, 1), (1, 0, 1), (1, 0, 0), (1, 1, 0)),
}
FACE_NORMAL = {
    "down": (0, -1, 0), "up": (0, 1, 0), "north": (0, 0, -1),
    "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0),
}
OPPOSITE = {"down": "up", "up": "down", "north": "south", "south": "north",
            "west": "east", "east": "west"}
AXIS_DIRS = np.array([FACE_NORMAL[f] for f in FACES], dtype=float)


def Rx(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def Ry(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def Rz(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def euler_matrix(x, y, z):
    """Element rotation as baked by 1.21.11 (rotate around X, then Y, then Z)."""
    return Rz(z) @ Ry(y) @ Rx(x)


def matrix_euler(R):
    """Inverse of euler_matrix. Returns (x, y, z) in degrees."""
    sb = max(-1.0, min(1.0, -R[2, 0]))
    b = math.asin(sb)
    if abs(math.cos(b)) > 1e-7:
        a = math.atan2(R[2, 1], R[2, 2])
        g = math.atan2(R[1, 0], R[0, 0])
    else:  # gimbal lock
        a = math.atan2(-R[1, 2], R[1, 1])
        g = 0.0
    return math.degrees(a), math.degrees(b), math.degrees(g)


def unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def frame(x_axis, y_hint):
    """Orthonormal right-handed frame (columns x, y, z) from an x axis and a y hint."""
    x = unit(x_axis)
    y = np.asarray(y_hint, dtype=float)
    y = unit(y - x * np.dot(x, y))
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=1)


def frame_yz(y_axis, z_hint):
    """Frame with exact local +Y axis, local +Z as close as possible to z_hint."""
    y = unit(y_axis)
    z = np.asarray(z_hint, dtype=float)
    z = unit(z - y * np.dot(y, z))
    x = np.cross(y, z)
    return np.stack([x, y, z], axis=1)


def rot_about(axis, deg):
    """Rodrigues rotation matrix (right handed)."""
    k = unit(axis)
    a = math.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * (K @ K)


def snap_direction(n):
    """Direction the game assigns to a quad (closest axis direction)."""
    i = int(np.argmax(AXIS_DIRS @ n))
    return FACES[i]


def _r(v, nd=4):
    v = round(float(v), nd)
    return 0.0 if v == 0 else v


class Elem:
    """One cuboid model element, possibly rotated around its own centre."""

    def __init__(self, center, R, size, faces=FACES, tex="body", mat=None,
                 name="", light=0, occluder=True, plane=None, origin=None):
        center = np.asarray(center, dtype=float)
        size = np.maximum(np.asarray(size, dtype=float), 0.0)
        self.name = name
        self.tex = tex
        self.mat = dict(mat or {})
        self.light = int(light)
        self.occluder = occluder and plane is None
        self.plane = plane          # None, or the axis index (0,1,2) that has zero size
        o = center if origin is None else np.asarray(origin, dtype=float)
        self.origin = np.array([_r(v) for v in o])
        self.frm = np.array([_r(c - s / 2) for c, s in zip(center, size)])
        self.to = np.array([_r(c + s / 2) for c, s in zip(center, size)])
        if R is None or np.allclose(R, np.eye(3), atol=1e-9):
            self.euler = None
            self.Rg = np.eye(3)
        else:
            ex, ey, ez = matrix_euler(R)
            self.euler = (_r(ex, 3), _r(ey, 3), _r(ez, 3))
            if all(abs(a) < 1e-6 for a in self.euler):
                self.euler = None
                self.Rg = np.eye(3)
            else:
                self.Rg = euler_matrix(*self.euler)
        if isinstance(faces, dict):
            self.faces = dict(faces)
        else:
            self.faces = {f: tex for f in faces}
        self.uv = {}       # face -> [u0, v0, u1, v1] (0-16 space)
        self.share = {}    # face -> face whose texture region it mirrors

    # ---- geometry -------------------------------------------------------
    @property
    def center(self):
        return self.world_pts(((self.frm + self.to) / 2)[None])[0]

    def corner_local(self, sel):
        return np.array([self.to[i] if sel[i] else self.frm[i] for i in range(3)])

    def world_pts(self, P):
        P = np.asarray(P, dtype=float)
        return (P - self.origin) @ self.Rg.T + self.origin

    def face_quad(self, f):
        return self.world_pts(np.array([self.corner_local(s) for s in FACE_CORNERS[f]]))

    def face_normal(self, f):
        return self.Rg @ np.array(FACE_NORMAL[f], dtype=float)

    def to_local(self, P):
        P = np.asarray(P, dtype=float)
        return (P - self.origin) @ self.Rg + self.origin

    def contains(self, P, eps=1e-4):
        L = self.to_local(P)
        return np.all((L >= self.frm - eps) & (L <= self.to + eps), axis=1)

    def bound_sphere(self):
        c = (self.frm + self.to) / 2
        r = np.linalg.norm(self.to - self.frm) / 2
        return self.world_pts(c[None])[0], r

    def size(self):
        return self.to - self.frm

    # ---- export -----------------------------------------------------------
    def to_json(self, light_override=None):
        d = {}
        if self.name:
            d["name"] = self.name
        d["from"] = [float(v) for v in self.frm]
        d["to"] = [float(v) for v in self.to]
        if self.euler is not None:
            d["rotation"] = {"origin": [float(v) for v in self.origin],
                             "x": self.euler[0], "y": self.euler[1], "z": self.euler[2]}
        light = self.light if light_override is None else light_override
        if light:
            d["light_emission"] = int(light)
        faces = {}
        for f in FACES:
            if f in self.faces:
                faces[f] = {"uv": [float(v) for v in self.uv[f]], "texture": "#" + self.faces[f]}
        d["faces"] = faces
        return d


def cull_hidden_faces(elems, samples=6, offset=0.035, log=None):
    """Removes faces whose whole surface is buried inside other solid elements."""
    spheres = [e.bound_sphere() for e in elems]
    occ = [i for i, e in enumerate(elems) if e.occluder]
    removed = 0
    g = (np.arange(samples) + 0.5) / samples
    g = np.concatenate([[0.02], g, [0.98]])
    S, T = np.meshgrid(g, g)
    S = S.ravel(); T = T.ravel()
    for i, e in enumerate(elems):
        for f in list(e.faces):
            Q = e.face_quad(f)
            n = e.face_normal(f)
            P = Q[0] + S[:, None] * (Q[3] - Q[0]) + T[:, None] * (Q[1] - Q[0]) + n * offset
            fc = P.mean(axis=0)
            fr = np.max(np.linalg.norm(P - fc, axis=1))
            covered = np.zeros(len(P), dtype=bool)
            for j in occ:
                if j == i:
                    continue
                c, r = spheres[j]
                if np.linalg.norm(c - fc) > r + fr:
                    continue
                covered |= elems[j].contains(P, eps=0.0)
                if covered.all():
                    break
            if covered.all():
                del e.faces[f]
                removed += 1
    kept = [e for e in elems if e.faces]
    if log:
        log(f"culled {removed} hidden faces, dropped {len(elems) - len(kept)} empty elements")
    return kept


# ---------------------------------------------------------------- z-fighting
def _poly_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _clip_area(A, B):
    if _poly_area(A) < 0:
        A = A[::-1]
    if _poly_area(B) < 0:
        B = B[::-1]
    out = [np.asarray(p, float) for p in A]
    for i in range(len(B)):
        c, d = B[i], B[(i + 1) % len(B)]
        inp, out = out, []
        if not inp:
            break
        dc = d - c

        def side(p):
            return dc[0] * (p[1] - c[1]) - dc[1] * (p[0] - c[0])
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            sp, sq = side(p), side(q)
            if sq >= -1e-9:
                if sp < -1e-9:
                    out.append(p + (q - p) * (sp / (sp - sq)))
                out.append(q)
            elif sp >= -1e-9:
                out.append(p + (q - p) * (sp / (sp - sq)))
    if len(out) < 3:
        return 0.0
    return abs(_poly_area(np.array(out)))


def coplanar_pairs(elems, tol=0.004, min_area=0.004, skip_kind="energy"):
    """Pairs of faces of different elements lying in the same plane and overlapping (z-fighting)."""
    faces = []
    for ei, e in enumerate(elems):
        if e.mat.get("kind") == skip_kind:
            continue
        for f in e.faces:
            Q = e.face_quad(f)
            n = e.face_normal(f)
            c = Q.mean(0)
            faces.append((ei, f, Q, n, float(n @ Q[0]), c, float(np.linalg.norm(Q - c, axis=1).max())))
    out = []
    for i in range(len(faces)):
        ei, fi, Qi, ni, di, ci, ri = faces[i]
        for j in range(i + 1, len(faces)):
            ej, fj, Qj, nj, dj, cj, rj = faces[j]
            if ej == ei or abs(di - dj) > tol or float(ni @ nj) < 0.9999:
                continue
            if np.linalg.norm(ci - cj) > ri + rj:
                continue
            u = unit(Qi[3] - Qi[0])
            v = np.cross(ni, u)
            A = np.stack([(Qi - Qi[0]) @ u, (Qi - Qi[0]) @ v], 1)
            B = np.stack([(Qj - Qi[0]) @ u, (Qj - Qi[0]) @ v], 1)
            ar = _clip_area(A, B)
            if ar > min_area:
                out.append((ei, fi, ej, fj, ar))
    return out


_AXIS = {"down": 1, "up": 1, "north": 2, "south": 2, "west": 0, "east": 0}


def fix_coplanar(elems, step=0.016, rounds=6, log=None):
    """Pulls one face of every coplanar overlapping pair inward so the depth test is stable."""
    total = 0
    for _ in range(rounds):
        pairs = coplanar_pairs(elems)
        if not pairs:
            break
        moved = set()
        for (ei, fi, ej, fj, ar) in pairs:
            if (ej, fj) in moved:
                continue
            e = elems[ej]
            ax = _AXIS[fj]
            if e.to[ax] - e.frm[ax] <= 2 * step:
                e, fj = elems[ei], fi
                ax = _AXIS[fj]
            if fj in ("up", "south", "east"):
                e.to[ax] = _r(e.to[ax] - step)
            else:
                e.frm[ax] = _r(e.frm[ax] + step)
            moved.add((ej, fj))
            total += 1
    if log:
        log(f"z-fighting fix: moved {total} faces, remaining pairs: {len(coplanar_pairs(elems))}")
    return elems
