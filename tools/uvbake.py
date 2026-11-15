"""UV layout (one unique texture region per visible face) and texture baking.

Each texel of a face region is mapped back to its exact 3D position on the model
(using the same FaceInfo vertex/UV assignment as the game), so procedural
materials can be painted continuously across many cuboids.
"""
import numpy as np
from mc import OPPOSITE


class Skyline:
    """Bottom-left skyline rectangle packer."""

    def __init__(self, width):
        self.W = width
        self.sky = [(0, 0, width)]   # (x, y, w)

    def _fit(self, i, w, h):
        x = self.sky[i][0]
        if x + w > self.W:
            return None
        y = 0
        rem = w
        j = i
        while rem > 0:
            if j >= len(self.sky):
                return None
            y = max(y, self.sky[j][1])
            rem -= self.sky[j][2]
            j += 1
        return y

    def insert(self, w, h):
        best = None
        for i in range(len(self.sky)):
            y = self._fit(i, w, h)
            if y is None:
                continue
            key = (y + h, self.sky[i][0])
            if best is None or key < best[0]:
                best = (key, i, y)
        if best is None:
            raise ValueError(f"rect {w}x{h} does not fit width {self.W}")
        _, i, y = best
        x = self.sky[i][0]
        new = (x, y + h, w)
        # rebuild skyline
        out = []
        for (sx, sy, sw) in self.sky:
            ex = sx + sw
            if ex <= x or sx >= x + w:
                out.append((sx, sy, sw))
            else:
                if sx < x:
                    out.append((sx, sy, x - sx))
                if ex > x + w:
                    out.append((x + w, sy, ex - (x + w)))
        out.append(new)
        out.sort()
        merged = []
        for s in out:
            if merged and merged[-1][1] == s[1] and merged[-1][0] + merged[-1][2] == s[0]:
                merged[-1] = (merged[-1][0], s[1], merged[-1][2] + s[2])
            else:
                merged.append(s)
        self.sky = merged
        return x, y

    def height(self):
        return max(s[1] for s in self.sky)


def face_px(e, f, density):
    Q = e.face_quad(f)
    w = np.linalg.norm(Q[3] - Q[0]) * density
    h = np.linalg.norm(Q[1] - Q[0]) * density
    return max(1, int(round(w))), max(1, int(round(h)))


def layout(elems, tex, density, width, pad=1, square=True, min_h=16):
    """Packs every visible face that uses texture variable `tex`. Returns (W, H, regions)."""
    items = []
    for ei, e in enumerate(elems):
        for f, t in e.faces.items():
            if t != tex or f in e.share:
                continue
            w, h = face_px(e, f, density)
            items.append((ei, f, w, h))
    items.sort(key=lambda it: (-(it[3] + 2 * pad), -(it[2] + 2 * pad)))
    sk = Skyline(width)
    regions = {}
    for ei, f, w, h in items:
        x, y = sk.insert(w + 2 * pad, h + 2 * pad)
        regions[(ei, f)] = (x + pad, y + pad, w, h)
    used = sk.height()
    H = max(min_h, used)
    # multiple of 32 keeps every mipmap level (Minecraft uses up to 4) integral
    H = (H + 31) // 32 * 32
    if square:
        H = max(H, width)
    return width, H, regions


def apply_uvs(elems, tex, W, H, regions):
    for (ei, f), (x, y, w, h) in regions.items():
        e = elems[ei]
        e.uv[f] = [x * 16.0 / W, y * 16.0 / H, (x + w) * 16.0 / W, (y + h) * 16.0 / H]
    # mirrored faces of zero-thickness planes share the region of their partner
    for e in elems:
        for f, src in e.share.items():
            if f in e.faces and src in e.uv:
                u0, v0, u1, v1 = e.uv[src]
                if f in ("north", "south", "east", "west"):
                    e.uv[f] = [u1, v0, u0, v1]
                else:
                    e.uv[f] = [u0, v1, u1, v0]


def face_samples(e, f, w, h, pad=1):
    """3D positions for the texel centres of a (w+2pad) x (h+2pad) region (padding extrapolated)."""
    Q = e.face_quad(f)
    s = (np.arange(-pad, w + pad) + 0.5) / w
    t = (np.arange(-pad, h + pad) + 0.5) / h
    S, T = np.meshgrid(s, t)
    P = Q[0] + S[..., None] * (Q[3] - Q[0]) + T[..., None] * (Q[1] - Q[0])
    return P, S, T


def bake(elems, tex, W, H, regions, material, frame=0, nframes=1, pad=1):
    img = np.zeros((H, W, 4), np.float32)
    for (ei, f), (x, y, w, h) in regions.items():
        e = elems[ei]
        P, S, T = face_samples(e, f, w, h, pad)
        n = e.face_normal(f)
        rgba = material(e, f, P, n, S, T, w, h, frame, nframes)
        img[y - pad:y + h + pad, x - pad:x + w + pad] = rgba
    return img
