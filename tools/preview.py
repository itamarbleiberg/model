"""Preview renders of the built pack (uses the exported textures + the exact element data).

usage:
  tools/run.sh tools/preview.py views VARIANT OUT.png      # turntable views with bloom
"""
import json
import math
import os
import pickle
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import mc
import render as rd
from build import ROOT, TEX_DIR, DISPLAY
from variants import VARIANTS, ORDER

FONT = "/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf"


def load_geometry():
    with open(os.path.join(ROOT, "build", "geometry.pkl"), "rb") as fh:
        return pickle.load(fh)["elems"]


def load_frames(path):
    img = np.array(Image.open(path).convert("RGBA"))
    meta_p = path + ".mcmeta"
    h = img.shape[1]
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p))["animation"]
        h = meta.get("height", min(img.shape[:2]))
        return [img[i * h:(i + 1) * h] for i in range(img.shape[0] // h)], meta
    return [img], None


def load_textures(key):
    tex = {}
    metas = {}
    for t in ("body", "blade", "energy"):
        frames, meta = load_frames(os.path.join(TEX_DIR, f"{key}_{t}.png"))
        tex[t] = frames
        metas[t] = meta
    return tex, metas


def frame_sequence(meta, nframes):
    """Expands an animation section into a per-tick frame index list."""
    if meta is None:
        return [0]
    ft = meta.get("frametime", 1)
    seq = []
    for fr in meta.get("frames", list(range(nframes))):
        if isinstance(fr, dict):
            seq += [fr["index"]] * fr.get("time", ft)
        else:
            seq += [fr] * ft
    return seq


def mesh_at(elems, tex, blade_frame=0, energy_frame=0):
    t = {"body": tex["body"][0], "blade": tex["blade"][blade_frame % len(tex["blade"])],
         "energy": tex["energy"][energy_frame % len(tex["energy"])]}
    return rd.Mesh(elems, t)


def studio_lights():
    return (mc.unit([-0.35, 0.75, 0.6]), mc.unit([0.5, 0.25, 0.45]))


def render_view(mesh, yaw, pitch, W, H, half=1.25, ss=2, bg=None, glow=1.0, target=(0.5, 0.56, 0.5)):
    V = rd.orbit(np.array(target), yaw, pitch, 4.0)
    Ws, Hs = W * ss, H * ss
    bgi = rd.gradient_bg(Ws, Hs) if bg is None else bg
    img, cov, emis = rd.rasterize(mesh, V, Ws, Hs, proj=("ortho", half), lights=studio_lights(), bg=bgi,
                                  emissive_out=True)
    if glow > 0:
        img = rd.bloom(img, emis, strength=0.45 * glow, radii=(2 * ss, 6 * ss, 16 * ss))
    return rd.downsample(img, ss), rd.downsample(cov[..., None], ss)[..., 0]


def views(key, out):
    elems = load_geometry()
    tex, metas = load_textures(key)
    mesh = mesh_at(elems, tex)
    tiles = []
    for yaw, pitch in ((0, 0), (32, 12), (90, 4), (180, 8), (-35, -18), (20, 60)):
        img, _ = render_view(mesh, yaw, pitch, 520, 640)
        tiles.append(rd.to_u8(img))
    grid = np.concatenate([np.concatenate(tiles[:3], 1), np.concatenate(tiles[3:], 1)], 0)
    Image.fromarray(grid).save(out)


def font(size, weight="Bold"):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def glow_spot(W, H, cx, cy, r, color, strength):
    y, x = np.mgrid[0:H, 0:W]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
    g = np.exp(-d * d) * strength
    return g[..., None] * np.array(color, np.float32)


def composite(bg, img, cov, x0, y0):
    h, w = img.shape[:2]
    a = cov[..., None]
    region = bg[y0:y0 + h, x0:x0 + w]
    region[:] = img * a + region * (1 - a)


def render_rgba(mesh, yaw, pitch, W, H, half, target=(0.5, 0.56, 0.5), ss=2, bloom=1.0):
    """Renders on black and returns (rgb premultiplied-ish, alpha incl. bloom)."""
    V = orbit_view(yaw, pitch, target)
    Ws, Hs = W * ss, H * ss
    img, cov, emis = rd.rasterize(mesh, V, Ws, Hs, proj=("ortho", half), lights=studio_lights(),
                                  bg=np.zeros((Hs, Ws, 3), np.float32), emissive_out=True)
    glow = np.zeros_like(img)
    if bloom > 0:
        glow = rd.bloom(np.zeros_like(img), emis, strength=0.5 * bloom, radii=(2 * ss, 6 * ss, 16 * ss))
    img = rd.downsample(img, ss); cov = rd.downsample(cov[..., None], ss)[..., 0]
    glow = rd.downsample(glow, ss)
    return img, cov, glow


def orbit_view(yaw, pitch, target):
    return rd.orbit(np.array(target), yaw, pitch, 4.0)


def make_preview(out):
    elems = load_geometry()
    W, H = 1920, 1080
    bg = rd.gradient_bg(W, H, top=(0.17, 0.18, 0.2), bottom=(0.07, 0.075, 0.085), vignette=0.45)
    slots = len(ORDER)
    cw = W // slots
    renders = []
    for i, key in enumerate(ORDER):
        v = VARIANTS[key]
        bg += glow_spot(W, H, cw * i + cw / 2, 520, 300, v["glow"], 0.12)
    for i, key in enumerate(ORDER):
        tex, metas = load_textures(key)
        mesh = mesh_at(elems, tex, 0 if key == "pause" else 4, 2)
        img, cov, glow = render_rgba(mesh, 24, 9, cw, 820, 1.15)
        x0 = cw * i
        composite(bg, img, cov, x0, 110)
        bg[110:110 + 820, x0:x0 + cw] += glow
    bg = np.clip(bg, 0, 1)
    im = Image.fromarray(rd.to_u8(bg))
    d = ImageDraw.Draw(im)
    d.text((W / 2, 52), "TIME BLADES", font=font(64, "Black"), fill=(244, 226, 196), anchor="mm")
    d.text((W / 2, 102), "3D item models  ·  Minecraft Java 1.21.11 resource pack  ·  inspired by Ninjago",
           font=font(24, "Medium"), fill=(170, 172, 178), anchor="mm")
    for i, key in enumerate(ORDER):
        v = VARIANTS[key]
        cx = cw * i + cw / 2
        col = tuple(int(255 * min(1, c * 0.85 + 0.15)) for c in v["glow"])
        d.text((cx, 960), v["title"], font=font(30, "Bold"), fill=col, anchor="mm")
        d.text((cx, 998), f"timeblades:{v['id']}", font=font(18, "Regular"), fill=(150, 152, 158), anchor="mm")
    im.save(out, optimize=True)


def make_pack_png(out, key="forward", size=256):
    elems = load_geometry()
    tex, metas = load_textures(key)
    mesh = mesh_at(elems, tex, 4, 2)
    v = VARIANTS[key]
    bg = rd.gradient_bg(size, size, top=(0.16, 0.17, 0.19), bottom=(0.07, 0.07, 0.08), vignette=0.5)
    bg += glow_spot(size, size, size / 2, size * 0.48, size * 0.42, v["glow"], 0.22)
    img, cov, glow = render_rgba(mesh, 26, 9, size, size, 1.04, target=(0.5, 0.56, 0.5), ss=3)
    composite(bg, img, cov, 0, 0)
    bg = np.clip(bg + glow, 0, 1)
    Image.fromarray(rd.to_u8(bg)).save(out, optimize=True)


def gui_icon_rgba(mesh, px):
    import handsim as hs
    qs = hs.QuadSet.from_mesh(mesh).transformed(rd.item_transform(DISPLAY, "gui"))
    V = np.eye(4); V[2, 3] = -10.0
    img, cov = rd.rasterize(qs, V, px, px, proj=("ortho", 0.5), lights=hs.gui_lights(False),
                            bg=np.zeros((px, px, 3), np.float32))
    return img, cov


def make_hotbar(out, scale=4):
    """Vanilla-like hotbar mock with the five blades (GUI scale `scale`)."""
    elems = load_geometry()
    slot = 20 * scale
    W = slot * 9 + 2 * scale
    H = slot + 2 * scale
    bar = np.zeros((H, W, 3), np.float32)
    bar[:] = (0.05, 0.05, 0.05)
    for s in range(9):
        x0 = scale + s * slot
        bar[scale:scale + slot, x0:x0 + slot] = (0.36, 0.36, 0.36)
        bar[scale + scale:scale + slot - scale, x0 + scale:x0 + slot - scale] = (0.18, 0.18, 0.2)
    for s, key in enumerate(ORDER):
        tex, metas = load_textures(key)
        mesh = mesh_at(elems, tex, 4, 2)
        img, cov = gui_icon_rgba(mesh, 16 * scale)
        x0 = scale + s * slot + 2 * scale
        composite(bar, img, cov, x0, 3 * scale)
    # selection frame around slot 1
    x0 = s0 = scale + 1 * slot - scale
    bar[0:scale, x0:x0 + slot + 2 * scale] = 0.92
    bar[H - scale:H, x0:x0 + slot + 2 * scale] = 0.92
    bar[:, x0:x0 + scale] = 0.92
    bar[:, x0 + slot + scale:x0 + slot + 2 * scale] = 0.92
    Image.fromarray(rd.to_u8(bar)).save(out, optimize=True)


def make_contexts(key, out):
    import handsim as hs
    elems = load_geometry()
    tex, metas = load_textures(key)
    mesh = mesh_at(elems, tex, 4, 2)
    fp = hs.first_person(mesh, DISPLAY, 960, 540)
    tp = hs.third_person(mesh, DISPLAY, 540, 540, view="front")
    tps = hs.third_person(mesh, DISPLAY, 540, 540, view="side")
    top = rd.to_u8(fp)
    mid = np.concatenate([rd.to_u8(tp)[:, 60:480], rd.to_u8(tps)[:, 0:540]], 1)
    mid = mid[:, :960]
    img = np.concatenate([top, mid], 0)
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    for (x, y, t) in ((14, 10, "first person (right hand)"), (14, 550, "third person"), (434, 550, "third person, side")):
        d.text((x, y), t, font=font(22, "SemiBold"), fill=(255, 255, 255))
    im.save(out, optimize=True)


def _anim_worker(args):
    key, out, n_ticks, W, H = args
    elems = load_geometry()
    tex, metas = load_textures(key)
    bseq = frame_sequence(metas["blade"], len(tex["blade"]))
    eseq = frame_sequence(metas["energy"], len(tex["energy"]))
    frames = []
    bg = rd.gradient_bg(W, H, top=(0.2, 0.21, 0.23), bottom=(0.09, 0.095, 0.1), vignette=0.4)
    for t in range(n_ticks):
        mesh = mesh_at(elems, tex, bseq[t % len(bseq)], eseq[t % len(eseq)])
        img, cov, glow = render_rgba(mesh, 24, 9, W, H, 1.15, ss=1, bloom=0.8)
        f = bg.copy()
        composite(f, img, cov, 0, 0)
        f = np.clip(f + glow, 0, 1)
        frames.append(Image.fromarray(rd.to_u8(f)))
    pal = frames[len(frames) // 2].quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=50, loop=0, optimize=False, disposal=1)
    return out


def anim_ticks(key):
    import math as _m
    elems_tex, metas = load_textures(key)
    b = len(frame_sequence(metas["blade"], len(elems_tex["blade"])))
    e = len(frame_sequence(metas["energy"], len(elems_tex["energy"])))
    return min(96, b * e // _m.gcd(b, e))


def make_anims(outdir, W=320, H=480):
    from multiprocessing import Pool
    jobs = [(k, os.path.join(outdir, f"anim_{k}.gif"), anim_ticks(k), W, H) for k in ORDER]
    with Pool(len(jobs)) as p:
        for r in p.imap_unordered(_anim_worker, jobs):
            print("wrote", r, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "views":
        views(sys.argv[2], sys.argv[3])
    elif cmd == "all":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        make_preview(os.path.join(outdir, "preview.png"))
        print("preview.png")
        make_hotbar(os.path.join(outdir, "hotbar_gui.png"))
        print("hotbar_gui.png")
        for k in ORDER:
            views(k, os.path.join(outdir, f"views_{k}.png"))
            make_contexts(k, os.path.join(outdir, f"in_hand_{k}.png"))
            print("views + in-hand", k)
        if "--no-anim" not in sys.argv:
            make_anims(outdir)
    elif cmd == "packpng":
        make_pack_png(sys.argv[2])
    elif cmd == "preview":
        make_preview(sys.argv[2])
    elif cmd == "hotbar":
        make_hotbar(sys.argv[2])
    elif cmd == "anims":
        make_anims(sys.argv[2])
