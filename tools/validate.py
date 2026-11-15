"""Static validation of the built pack + (optionally) the real 1.21.11 parsers via tools/mcvalidate.

Checks:
  * every JSON file parses; pack.mcmeta has min/max_format 75
  * item definitions point to existing models; models reference only defined texture variables
  * every texture path exists (no missing textures), all live under textures/item (one atlas)
  * element bounds (-16..32), rotation format, light_emission range, >= 1 face per element
  * UVs inside 0..16 and inside the texture frame; solid faces never sample transparent texels
  * animated textures: strip height = n * frame height, frame indices valid
  * display transforms: translation within +-80, scale <= 4
"""
import glob
import json
import os
import subprocess
import sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "pack", "NinjagoTimeBlades")
NS = "timeblades"
problems = []
notes = []


def err(msg):
    problems.append(msg)
    print("  ERROR", msg)


def tex_path(ref):
    ns, path = ref.split(":", 1) if ":" in ref else ("minecraft", ref)
    return os.path.join(PACK, "assets", ns, "textures", path + ".png")


def load_texture(ref):
    p = tex_path(ref)
    img = np.array(Image.open(p).convert("RGBA"))
    meta_p = p + ".mcmeta"
    fh = img.shape[0]
    fw = img.shape[1]
    nframes = 1
    if os.path.exists(meta_p):
        anim = json.load(open(meta_p))["animation"]
        fw = anim.get("width", min(img.shape[:2]))
        fh = anim.get("height", min(img.shape[:2]))
        if img.shape[0] % fh or img.shape[1] % fw:
            err(f"{os.path.basename(p)}: size {img.shape[1]}x{img.shape[0]} not a multiple of frame {fw}x{fh}")
        nframes = (img.shape[0] // fh) * (img.shape[1] // fw)
        for fr in anim.get("frames", []):
            idx = fr["index"] if isinstance(fr, dict) else fr
            if not 0 <= idx < nframes:
                err(f"{os.path.basename(p)}: frame index {idx} out of range (0..{nframes - 1})")
        ft = anim.get("frametime", 1)
        if ft < 1:
            err(f"{os.path.basename(p)}: frametime {ft} < 1")
    frames = [img[i * fh:(i + 1) * fh, :fw] for i in range(nframes)]
    return frames, (fw, fh)


def zfight_pairs():
    import pickle
    gp = os.path.join(ROOT, "build", "geometry.pkl")
    if not os.path.exists(gp):
        return None
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import mc
    elems = pickle.load(open(gp, "rb"))["elems"]
    return [(f"{elems[a].name}.{fa}", f"{elems[b].name}.{fb}", ar) for (a, fa, b, fb, ar) in mc.coplanar_pairs(elems)]


def main():
    print("pack:", PACK)
    # ---- files present
    for f in ("pack.mcmeta", "pack.png", "README.md", "commands.txt"):
        if not os.path.exists(os.path.join(PACK, f)):
            err(f"missing {f}")
    # ---- every json parses
    jfiles = glob.glob(os.path.join(PACK, "**", "*.json"), recursive=True) + \
        glob.glob(os.path.join(PACK, "**", "*.mcmeta"), recursive=True)
    for p in jfiles:
        try:
            json.load(open(p, encoding="utf-8"))
        except Exception as e:
            err(f"invalid JSON {os.path.relpath(p, PACK)}: {e}")
    print(f"  {len(jfiles)} JSON/mcmeta files parse")
    meta = json.load(open(os.path.join(PACK, "pack.mcmeta")))["pack"]
    if meta.get("min_format") != 75 or meta.get("max_format") != 75:
        err(f"pack.mcmeta formats {meta.get('min_format')}..{meta.get('max_format')} (expected 75)")
    if "supported_formats" in meta:
        err("supported_formats must not be present for 1.21.9+ only packs")
    icon = Image.open(os.path.join(PACK, "pack.png"))
    print(f"  pack.png {icon.size[0]}x{icon.size[1]} {icon.mode}")
    # ---- items -> models
    items = sorted(glob.glob(os.path.join(PACK, "assets", NS, "items", "*.json")))
    if len(items) != 5:
        err(f"expected 5 item definitions, found {len(items)}")
    total_faces = 0
    for ip in items:
        item = json.load(open(ip))
        mref = item["model"]["model"]
        if item["model"]["type"] != "minecraft:model":
            err(f"{os.path.basename(ip)}: unexpected type")
        ns, path = mref.split(":", 1)
        mp = os.path.join(PACK, "assets", ns, "models", path + ".json")
        if not os.path.exists(mp):
            err(f"{os.path.basename(ip)} -> missing model {mref}")
            continue
        model = json.load(open(mp))
        key = os.path.basename(ip).replace("_time_blade.json", "")
        textures = model.get("textures", {})
        for var, ref in textures.items():
            if not os.path.exists(tex_path(ref)):
                err(f"{mref}: texture '{var}' -> {ref} missing")
            if "/textures/item/" not in tex_path(ref).replace("\\", "/"):
                err(f"{mref}: texture {ref} is not in the item atlas")
            if f"/{key}_" not in ref:
                err(f"{mref}: texture {ref} belongs to another blade")
        if "particle" not in textures:
            err(f"{mref}: no particle texture")
        loaded = {var: load_texture(ref) for var, ref in textures.items()}
        n_el = len(model["elements"])
        lights = set()
        uv_bad = 0
        holes = 0
        for e in model["elements"]:
            for v in e["from"] + e["to"]:
                if not -16 <= v <= 32:
                    err(f"{mref} {e.get('name')}: coordinate {v} outside -16..32")
            if "rotation" in e:
                r = e["rotation"]
                if "origin" not in r or not all(k in r for k in ("x", "y", "z")):
                    err(f"{mref} {e.get('name')}: rotation needs origin + x/y/z")
            le = e.get("light_emission", 0)
            lights.add(le)
            if not (isinstance(le, int) and 0 <= le <= 15):
                err(f"{mref} {e.get('name')}: light_emission {le}")
            if not e.get("faces"):
                err(f"{mref} {e.get('name')}: no faces")
            for fname, face in e["faces"].items():
                total_faces += 1
                var = face["texture"].lstrip("#")
                if var not in textures:
                    err(f"{mref} {e.get('name')}.{fname}: undefined texture #{var}")
                    continue
                u0, v0, u1, v1 = face["uv"]
                if not all(0 <= c <= 16 for c in face["uv"]):
                    uv_bad += 1
                    continue
                frames, (fw, fh) = loaded[var]
                x0, x1 = sorted((u0 / 16 * fw, u1 / 16 * fw))
                y0, y1 = sorted((v0 / 16 * fh, v1 / 16 * fh))
                xa, xb = int(round(x0)), int(round(x1))
                ya, yb = int(round(y0)), int(round(y1))
                if xb <= xa or yb <= ya:
                    err(f"{mref} {e.get('name')}.{fname}: empty UV rect")
                    continue
                if var != "energy":
                    for fr in frames:
                        if (fr[ya:yb, xa:xb, 3] < 255).any():
                            holes += 1
                            break
        if uv_bad:
            err(f"{mref}: {uv_bad} faces with UV outside 0..16")
        if holes:
            err(f"{mref}: {holes} solid faces sample transparent texels (would look like holes)")
        for ctx, d in model["display"].items():
            if any(abs(t) > 80 for t in d.get("translation", [0, 0, 0])):
                err(f"{mref}: display {ctx} translation out of range")
            if any(s > 4 for s in d.get("scale", [1, 1, 1])):
                err(f"{mref}: display {ctx} scale > 4")
            for k in ("rotation", "translation", "scale"):
                if k in d and len(d[k]) != 3:
                    err(f"{mref}: display {ctx}.{k} must have 3 values")
        need = {"firstperson_righthand", "firstperson_lefthand", "thirdperson_righthand",
                "thirdperson_lefthand", "gui", "ground", "fixed", "head", "on_shelf"}
        if need - set(model["display"]):
            err(f"{mref}: missing display contexts {need - set(model['display'])}")
        tex_desc = ", ".join(f"{v}: {loaded[v][1][0]}x{loaded[v][1][1]} x{len(loaded[v][0])}f" for v in sorted(loaded))
        print(f"  {mref}: {n_el} elements, light_emission {sorted(lights)}, textures [{tex_desc}]")
    print(f"  {total_faces} faces checked")
    # ---- give commands fit the chat box
    for line in open(os.path.join(PACK, "commands.txt"), encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("/give") and len(line) > 256:
            err(f"command longer than the 256-character chat limit ({len(line)}): {line[:60]}...")
    # ---- textures that nothing uses
    used = set()
    for mp in glob.glob(os.path.join(PACK, "assets", NS, "models", "item", "*.json")):
        used |= {tex_path(r) for r in json.load(open(mp))["textures"].values()}
    for p in glob.glob(os.path.join(PACK, "assets", NS, "textures", "**", "*.png"), recursive=True):
        if p not in used:
            err(f"unused texture {os.path.relpath(p, PACK)}")
    # ---- z-fighting: coplanar overlapping faces of different solid elements
    zf = zfight_pairs()
    if zf is None:
        print("  (no build/geometry.pkl - skipping z-fighting check)")
    elif zf:
        for a, b, area in zf[:10]:
            print(f"    coplanar overlap {area:.3f} units^2: {a} / {b}")
        err(f"{len(zf)} coplanar overlapping face pairs (z-fighting)")
    else:
        print("  no coplanar overlapping faces between solid elements (no z-fighting)")
    # ---- the real game parsers
    if "--no-game" not in sys.argv:
        cache = "/projects/sandbox/.cache"
        jar = os.path.join(cache, "client.jar")
        if os.path.exists(jar):
            cp = ":".join([jar] + sorted(glob.glob(os.path.join(cache, "libs", "*.jar"))))
            out = "/dev/shm/gp"
            os.makedirs(out, exist_ok=True)
            subprocess.run(["javac", "-nowarn", "-cp", cp, "-d", out,
                            os.path.join(ROOT, "tools", "mcvalidate", "GameParse.java")],
                           check=True, capture_output=True)
            r = subprocess.run(["java", "-cp", out + ":" + cp, "tbvalidate.GameParse", PACK],
                               capture_output=True, text=True, cwd="/dev/shm")
            lines = [l.split("[STDOUT]: ", 1)[-1] for l in (r.stdout + r.stderr).splitlines() if "[STDOUT]" in l]
            for l in lines:
                print("  [game] " + l[:200])
            if r.returncode != 0:
                err("Minecraft 1.21.11 parsers reported errors")
        else:
            print("  (client.jar not cached - skipping game parser check)")
    print()
    if problems:
        print(f"VALIDATION FAILED: {len(problems)} problem(s)")
        sys.exit(1)
    print("VALIDATION PASSED")


if __name__ == "__main__":
    main()
