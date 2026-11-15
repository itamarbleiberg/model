"""Small software rasteriser that renders Minecraft item models the way the game does.

* quads are built from the same Elem objects that are exported to JSON
* textures are sampled with nearest filtering, alpha < 0.1 is discarded
* every quad is lit with the game's item diffuse model using the *snapped*
  quad direction (min(1, 0.4 + 0.6 * (max(0, L0.n) + max(0, L1.n))))
* quads are sorted back to front and blended (translucent item sheet behaviour)
* display transforms follow ItemTransform.apply() from 1.21.11
"""
import math
import numpy as np
from mc import FACES, FACE_NORMAL, snap_direction, Rx, Ry, Rz, unit

# ---------------------------------------------------------------------------
# lights (com.mojang.blaze3d.platform.Lighting, 1.21.11)
L0 = unit([0.2, 1.0, -0.7])
L1 = unit([-0.2, 1.0, 0.7])


def _rot_y(a):
    return Ry(math.degrees(a))


def _rot_x(a):
    return Rx(math.degrees(a))


def items_flat_lights():
    M = _rot_y(-0.3926991) @ _rot_x(2.3561945)
    return M @ L0, M @ L1


def items_3d_lights():
    # Matrix4f().scaling(1,-1,1).rotateYXZ(1.0821041, 3.2375858, 0).rotateYXZ(-0.3926991, 2.3561945, 0)
    S = np.diag([1.0, -1.0, 1.0])
    M = S @ (_rot_y(1.0821041) @ _rot_x(3.2375858)) @ (_rot_y(-0.3926991) @ _rot_x(2.3561945))
    return M @ L0, M @ L1


def mc_light(n, lights):
    a, b = lights
    return min(1.0, 0.4 + 0.6 * (max(0.0, float(np.dot(a, n))) + max(0.0, float(np.dot(b, n)))))


# ---------------------------------------------------------------------------
def mat4(R=None, t=None, s=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if s is not None:
        M[:3, :3] = M[:3, :3] @ np.diag(s)
    if t is not None:
        M[:3, 3] = t
    return M


def T(x, y, z):
    return mat4(t=[x, y, z])


def S(x, y=None, z=None):
    if y is None:
        y = z = x
    return mat4(s=[x, y, z])


def R4(R):
    return mat4(R=R)


def item_transform(display, ctx, left=False):
    """ItemTransform.apply(): translate, rotate XYZ, scale, then translate(-0.5)."""
    d = display.get(ctx)
    if d is None:
        return T(-0.5, -0.5, -0.5)
    rot = list(d.get("rotation", [0, 0, 0]))
    tr = [v / 16.0 for v in d.get("translation", [0, 0, 0])]
    sc = d.get("scale", [1, 1, 1])
    if left:
        rot[1] = -rot[1]; rot[2] = -rot[2]; tr[0] = -tr[0]
    Rm = Rx(rot[0]) @ Ry(rot[1]) @ Rz(rot[2])   # Quaternionf.rotationXYZ
    return T(*tr) @ R4(Rm) @ S(*sc) @ T(-0.5, -0.5, -0.5)


# ---------------------------------------------------------------------------
class Mesh:
    """Quads of a model: positions in block units (model / 16)."""

    def __init__(self, elems, textures, frame=0):
        P, UV, TI, N, LE, EW = [], [], [], [], [], []
        self.tex_names = sorted(textures)
        self.textures = []
        for name in self.tex_names:
            img = textures[name]
            if isinstance(img, list):
                img = img[frame % len(img)]
            self.textures.append(np.asarray(img, dtype=np.float32) / 255.0)
        index = {n: i for i, n in enumerate(self.tex_names)}
        for e in elems:
            for f, tex in e.faces.items():
                q = e.face_quad(f) / 16.0
                u0, v0, u1, v1 = e.uv[f]
                th, tw = self.textures[index[tex]].shape[:2]
                us = np.array([u0, u0, u1, u1]) / 16.0 * tw
                vs = np.array([v0, v1, v1, v0]) / 16.0 * th
                P.append(q)
                UV.append(np.stack([us, vs], axis=1))
                TI.append(index[tex])
                N.append(np.array(FACE_NORMAL[snap_direction(e.face_normal(f))], dtype=float))
                LE.append(e.light)
                kind = e.mat.get("kind")
                EW.append(1.0 if kind == "energy" else (0.3 if (kind == "blade" and e.light >= 10) else 0.0))
        self.P = np.array(P)
        self.UV = np.array(UV)
        self.TI = np.array(TI)
        self.N = np.array(N)
        self.light = np.array(LE)
        self.emis_w = np.array(EW)


def rasterize(mesh, M, W, H, proj=("persp", 70.0), lights=None, bg=None,
              shade_override=None, emissive_out=False, near=0.02, flat=False):
    """Draw the mesh transformed by 4x4 M into camera space (camera looks down -Z)."""
    if bg is None:
        img = np.zeros((H, W, 3), np.float32)
    else:
        img = np.array(bg, np.float32).copy()
    alpha_cov = np.zeros((H, W), np.float32)
    depth = np.full((H, W), np.inf, np.float32)
    emis = np.zeros((H, W, 3), np.float32) if emissive_out else None
    if len(mesh.P) == 0:
        return img
    P = mesh.P.reshape(-1, 3)
    Ph = np.concatenate([P, np.ones((len(P), 1))], axis=1) @ M.T
    Pc = Ph[:, :3].reshape(-1, 4, 3)
    Nrm = mesh.N @ M[:3, :3].T
    Nrm /= np.linalg.norm(Nrm, axis=1, keepdims=True) + 1e-12
    if lights is None:
        lights = (L0, L1)
    shade = np.array([mc_light(n, lights) for n in Nrm]) if not flat else np.ones(len(Nrm))
    aspect = W / H
    if proj[0] == "persp":
        f = 1.0 / math.tan(math.radians(proj[1]) / 2)
        z = -Pc[..., 2]
        valid = np.all(z > near, axis=1)
        zs = np.where(z > near, z, near)
        sx = (f / aspect * Pc[..., 0] / zs * 0.5 + 0.5) * W
        sy = (1 - (f * Pc[..., 1] / zs * 0.5 + 0.5)) * H
        wv = zs
    else:
        hh = proj[1]
        z = -Pc[..., 2]
        valid = np.ones(len(Pc), bool)
        sx = (Pc[..., 0] / (hh * aspect) * 0.5 + 0.5) * W
        sy = (1 - (Pc[..., 1] / hh * 0.5 + 0.5)) * H
        wv = np.ones_like(z)
    order = np.argsort(-z.mean(axis=1))
    for qi in order:
        if not valid[qi]:
            continue
        tex = mesh.textures[mesh.TI[qi]]
        th, tw = tex.shape[:2]
        for tri in ((0, 1, 2), (0, 2, 3)):
            xs = sx[qi, tri]; ys = sy[qi, tri]
            x0 = max(int(math.floor(xs.min())), 0); x1 = min(int(math.ceil(xs.max())), W - 1)
            y0 = max(int(math.floor(ys.min())), 0); y1 = min(int(math.ceil(ys.max())), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            area = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
            if abs(area) < 1e-9:
                continue
            # back-face culling (translucentCull): quads are CCW when facing the viewer
            if area > 0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((xs[1] - gx) * (ys[2] - gy) - (xs[2] - gx) * (ys[1] - gy)) / area
            w1 = ((xs[2] - gx) * (ys[0] - gy) - (xs[0] - gx) * (ys[2] - gy)) / area
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            iw = 1.0 / wv[qi, tri]
            denom = w0 * iw[0] + w1 * iw[1] + w2 * iw[2]
            zz = (w0 * z[qi, tri[0]] * iw[0] + w1 * z[qi, tri[1]] * iw[1] + w2 * z[qi, tri[2]] * iw[2]) / denom
            dsub = depth[y0:y1 + 1, x0:x1 + 1]
            m = inside & (zz < dsub - 1e-7)
            if not m.any():
                continue
            uvq = mesh.UV[qi, list(tri)]
            uu = (w0 * uvq[0, 0] * iw[0] + w1 * uvq[1, 0] * iw[1] + w2 * uvq[2, 0] * iw[2]) / denom
            vv = (w0 * uvq[0, 1] * iw[0] + w1 * uvq[1, 1] * iw[1] + w2 * uvq[2, 1] * iw[2]) / denom
            ui = np.clip(np.floor(uu).astype(int), 0, tw - 1)
            vi = np.clip(np.floor(vv).astype(int), 0, th - 1)
            texel = tex[vi, ui]
            a = texel[..., 3]
            m &= a >= 0.1
            if not m.any():
                continue
            s = shade[qi] if shade_override is None else shade_override
            col = texel[..., :3] * s
            isub = img[y0:y1 + 1, x0:x1 + 1]
            am = a[..., None]
            isub[m] = (col * am + isub * (1 - am))[m]
            dsub[m] = zz[m]
            asub = alpha_cov[y0:y1 + 1, x0:x1 + 1]
            asub[m] = 1 - (1 - asub[m]) * (1 - a[m])
            if emis is not None:
                esub = emis[y0:y1 + 1, x0:x1 + 1]
                if mesh.emis_w[qi] > 0:
                    lum = texel[..., :3] * mesh.emis_w[qi]
                    esub[m] = (lum * am + esub * (1 - am))[m]
                else:
                    esub[m] = (esub * (1 - am))[m]
    if emissive_out:
        return img, alpha_cov, emis
    return img, alpha_cov


# ---------------------------------------------------------------------------
def look_at(eye, target, up=(0, 1, 0)):
    eye = np.asarray(eye, float); target = np.asarray(target, float)
    f = unit(target - eye)
    r = unit(np.cross(f, up))
    u = np.cross(r, f)
    V = np.eye(4)
    V[0, :3] = r; V[1, :3] = u; V[2, :3] = -f
    V[:3, 3] = -V[:3, :3] @ eye
    return V


def orbit(target, yaw, pitch, dist):
    """Camera orbiting the target. yaw 0 = looking from +Z (model front) toward -Z."""
    y, p = math.radians(yaw), math.radians(pitch)
    eye = np.array([math.sin(y) * math.cos(p), math.sin(p), math.cos(y) * math.cos(p)]) * dist + target
    return look_at(eye, target)


def box_blur(a, r):
    if r <= 0:
        return a
    k = 2 * r + 1
    pad = np.pad(a, ((r, r), (r, r), (0, 0)), mode="constant")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0), (0, 0)))
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / (k * k)


def bloom(img, emis, strength=1.0, radii=(3, 9, 22)):
    g = np.zeros_like(img)
    for i, r in enumerate(radii):
        b = emis
        for _ in range(3):
            b = box_blur(b, r)
        g += b * (0.9 / (i + 1))
    return np.clip(img + g * strength, 0, 1)


def downsample(img, k):
    if k == 1:
        return img
    H, W = img.shape[:2]
    return img[:H - H % k, :W - W % k].reshape(H // k, k, W // k, k, -1).mean(axis=(1, 3))


def gradient_bg(W, H, top=(0.25, 0.26, 0.27), bottom=(0.16, 0.17, 0.18), vignette=0.35):
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(-1, 1, W)[None, :, None]
    yy = np.linspace(-1, 1, H)[:, None, None]
    base = np.array(top) * (1 - y) + np.array(bottom) * y
    v = 1 - vignette * np.clip((x ** 2 + yy ** 2) / 2, 0, 1)
    return (base * v).astype(np.float32) * np.ones((H, W, 3), np.float32)


def to_u8(img):
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
