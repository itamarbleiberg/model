"""Builds the Ninjago Time Blades resource pack for Minecraft Java 1.21.11.

usage: tools/run.sh tools/build.py [--quick] [--only VARIANT]
"""
import json
import os
import shutil
import sys
import time
import numpy as np
from PIL import Image

import design
import mc
import uvbake
from materials import Materials
from variants import VARIANTS, ORDER, blade_mcmeta, energy_mcmeta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_NAME = "NinjagoTimeBlades"
PACK = os.path.join(ROOT, "pack", PACK_NAME)
NS = "timeblades"
TEX_DIR = os.path.join(PACK, "assets", NS, "textures", "item", "time_blade")
MODEL_DIR = os.path.join(PACK, "assets", NS, "models", "item")
ITEM_DIR = os.path.join(PACK, "assets", NS, "items")
BUILD = os.path.join(ROOT, "build")

DENSITY = {"body": 4, "blade": 4, "energy": 4}
WIDTH = {"body": 256, "blade": 256, "energy": 256}

# Display transforms (shared by all five blades). Tuned with tools/preview.py.
DISPLAY = json.load(open(os.path.join(os.path.dirname(__file__), "display.json")))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def geometry():
    elems, curve = design.build()
    log(f"elements built: {len(elems)}")
    elems = mc.cull_hidden_faces(elems, log=log)
    mc.fix_coplanar(elems, log=log)
    layouts = {}
    for tex in ("body", "blade", "energy"):
        W, H, reg = uvbake.layout(elems, tex, DENSITY[tex], WIDTH[tex], square=False)
        uvbake.apply_uvs(elems, tex, W, H, reg)
        layouts[tex] = (W, H, reg)
        log(f"texture '{tex}': {W}x{H} per frame, {len(reg)} face regions")
    return elems, curve, layouts


def to_png(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def bake_variant(key, elems, curve, layouts, quick=False):
    v = VARIANTS[key]
    mats = Materials(v, curve)
    out = {}
    W, H, reg = layouts["body"]
    out["body"] = uvbake.bake(elems, "body", W, H, reg, mats)
    for tex, nfk in (("blade", "blade_frames"), ("energy", "energy_frames")):
        W, H, reg = layouts[tex]
        n = 1 if quick else v[nfk]
        out[tex] = [uvbake.bake(elems, tex, W, H, reg, mats, frame=k, nframes=v[nfk]) for k in range(n)]
    return out


def write_textures(key, baked):
    v = VARIANTS[key]
    os.makedirs(TEX_DIR, exist_ok=True)
    paths = {}
    p = os.path.join(TEX_DIR, f"{key}_body.png")
    to_png(baked["body"]).save(p, optimize=True)
    paths["body"] = p
    for tex in ("blade", "energy"):
        frames = baked[tex]
        strip = np.concatenate(frames, axis=0)
        p = os.path.join(TEX_DIR, f"{key}_{tex}.png")
        to_png(strip).save(p, optimize=True)
        paths[tex] = p
        meta = blade_mcmeta(v) if tex == "blade" else energy_mcmeta(v)
        h = frames[0].shape[0]
        w = frames[0].shape[1]
        if h != w:
            meta["animation"]["width"] = w
            meta["animation"]["height"] = h
        if len(frames) > 1:
            with open(p + ".mcmeta", "w") as fh:
                json.dump(meta, fh, indent=2)
        elif os.path.exists(p + ".mcmeta"):
            os.remove(p + ".mcmeta")
    return paths


def model_json(key, elems):
    v = VARIANTS[key]
    tex = lambda t: f"{NS}:item/time_blade/{key}_{t}"
    light_blade = 0 if v["metal_blade"] else 15
    out_elems = []
    for e in elems:
        lo = None
        if e.mat.get("kind") == "blade":
            lo = light_blade
        out_elems.append(e.to_json(light_override=lo))
    return {
        "credit": "Ninjago Time Blades fan resource pack - original model, generated with tools/build.py",
        "gui_light": "front",
        "textures": {
            "particle": tex("body"),
            "body": tex("body"),
            "blade": tex("blade"),
            "energy": tex("energy"),
        },
        "elements": out_elems,
        "display": DISPLAY,
    }


def item_json(key):
    v = VARIANTS[key]
    return {
        "model": {"type": "minecraft:model", "model": f"{NS}:item/{v['id']}"},
        "swap_animation_scale": 1.6,
    }


def write_json(path, data, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact and "elements" in data:
            # readable but small: one element / display context per line
            head = {k: v for k, v in data.items() if k not in ("elements", "display")}
            parts = ["{"]
            for k, v in head.items():
                parts.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
            parts.append('  "elements": [')
            els = [json.dumps(e, separators=(",", ":")) for e in data["elements"]]
            parts.append(",\n".join("    " + e for e in els))
            parts.append("  ],")
            parts.append('  "display": {')
            disp = [f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in data["display"].items()]
            parts.append(",\n".join(disp))
            parts.append("  }")
            parts.append("}")
            fh.write("\n".join(parts) + "\n")
        else:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")


def main():
    quick = "--quick" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    elems, curve = None, None
    elems, curve, layouts = geometry()
    os.makedirs(BUILD, exist_ok=True)
    for key in ORDER:
        if only and key != only:
            continue
        t0 = time.time()
        baked = bake_variant(key, elems, curve, layouts, quick)
        write_textures(key, baked)
        v = VARIANTS[key]
        write_json(os.path.join(MODEL_DIR, f"{v['id']}.json"), model_json(key, elems), compact=True)
        write_json(os.path.join(ITEM_DIR, f"{v['id']}.json"), item_json(key))
        log(f"{key}: baked + written in {time.time() - t0:.1f}s")
    # save geometry for preview / validation tools
    import pickle
    with open(os.path.join(BUILD, "geometry.pkl"), "wb") as fh:
        pickle.dump({"elems": elems, "layouts": {k: (W, H) for k, (W, H, _) in layouts.items()}}, fh)
    log("done")


if __name__ == "__main__":
    main()
