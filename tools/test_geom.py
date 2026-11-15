"""Quick geometry check: flat debug colours, several camera angles."""
import sys
import numpy as np
from PIL import Image
import design
import mc
import uvbake
import render as rd

DEBUG = {
    "blade": (0.25, 0.85, 0.35), "energy": (1.0, 1.0, 1.0), "plate": (0.72, 0.42, 0.25),
    "back": (0.55, 0.33, 0.2), "core": (0.15, 0.08, 0.05), "rivet": (0.95, 0.8, 0.5),
    "crown": (0.85, 0.52, 0.32), "cuff": (0.6, 0.38, 0.22), "flange": (0.75, 0.5, 0.3),
    "rim": (0.7, 0.45, 0.28), "cuffinner": (0.1, 0.06, 0.04), "grip": (0.3, 0.2, 0.15),
    "neck": (0.4, 0.25, 0.15),
}


def debug_material(e, f, P, n, S, T, w, h, frame, nframes):
    kind = e.mat.get("kind")
    c = np.array(DEBUG.get(kind, (1, 0, 1)), np.float32)
    out = np.ones(P.shape[:2] + (4,), np.float32)
    lam = 0.55 + 0.45 * max(0.0, float(np.dot(n, mc.unit([-0.4, 0.7, 0.6]))))
    out[..., :3] = c * lam
    # edge lines to see the tiles
    edge = (S < 1.0 / max(w, 1)) | (T < 1.0 / max(h, 1))
    out[edge, :3] *= 0.7
    if kind == "energy":
        out[..., 3] = 0.0
        if "--sparks" in sys.argv:
            out[..., 3] = 0.25
    if kind == "blade" and e.mat.get("part") == "fin":
        out[..., :3] = np.array([0.5, 1.0, 0.55]) * lam
    if kind == "crown" and e.mat.get("part") in ("roof", "vee"):
        out[..., :3] = np.array([0.95, 0.6, 0.38]) * lam
    if kind == "crown" and e.mat.get("part") == "spine":
        out[..., :3] = np.array([1.0, 0.75, 0.5]) * lam
    return out


def main():
    elems, curve = design.build()
    print("elements before cull:", len(elems))
    elems = mc.cull_hidden_faces(elems, log=print)
    print("elements after cull:", len(elems), "faces:", sum(len(e.faces) for e in elems))
    texs = {}
    for tex, dens, width in (("body", 4, 256), ("blade", 4, 256), ("energy", 4, 256)):
        W, H, reg = uvbake.layout(elems, tex, dens, width)
        uvbake.apply_uvs(elems, tex, W, H, reg)
        texs[tex] = (uvbake.bake(elems, tex, W, H, reg, debug_material) * 255).astype(np.uint8)
        print(tex, W, H, len(reg))
    mesh = rd.Mesh(elems, texs)
    views = [("front", 0, 0), ("q34", 35, 15), ("side", 90, 5), ("back", 180, 10), ("top", 20, 70),
             ("low", -30, -25)]
    tiles = []
    for name, yaw, pitch in views:
        V = rd.orbit(np.array([0.5, 0.58, 0.5]), yaw, pitch, 4.0)
        img, _ = rd.rasterize(mesh, V, 600, 700, proj=("ortho", 1.25),
                              bg=rd.gradient_bg(600, 700), lights=(mc.unit([-0.3, 0.8, 0.6]), mc.unit([0.4, 0.2, 0.5])))
        tiles.append(rd.to_u8(img))
    row = np.concatenate(tiles[:3], axis=1)
    row2 = np.concatenate(tiles[3:], axis=1)
    Image.fromarray(np.concatenate([row, row2], axis=0)).save(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "previews/_geom.png")


if __name__ == "__main__":
    main()
