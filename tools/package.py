"""Zips the pack (pack.mcmeta at the archive root) and verifies the archive."""
import json
import os
import shutil
import zipfile
from build import PACK, ROOT

OUT = os.path.join(ROOT, "dist", "NinjagoTimeBlades_1.21.11.zip")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    prev = os.path.join(ROOT, "previews", "preview.png")
    if os.path.exists(prev):
        shutil.copy(prev, os.path.join(PACK, "preview.png"))
    if os.path.exists(OUT):
        os.remove(OUT)
    files = []
    for base, dirs, names in os.walk(PACK):
        dirs.sort()
        for n in sorted(names):
            full = os.path.join(base, n)
            files.append((full, os.path.relpath(full, PACK).replace(os.sep, "/")))
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for full, arc in files:
            info = zipfile.ZipInfo(arc, date_time=(2026, 11, 14, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as fh:
                z.writestr(info, fh.read())
    # verify
    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        assert bad is None, f"corrupt entry {bad}"
        names = z.namelist()
        assert "pack.mcmeta" in names, "pack.mcmeta must be at the zip root"
        assert "pack.png" in names
        for n in names:
            if n.endswith((".json", ".mcmeta")):
                json.loads(z.read(n).decode("utf-8"))
        models = [n for n in names if n.startswith("assets/timeblades/models/item/")]
        items = [n for n in names if n.startswith("assets/timeblades/items/")]
        pngs = [n for n in names if n.startswith("assets/timeblades/textures/") and n.endswith(".png")]
        metas = [n for n in names if n.endswith(".png.mcmeta")]
    size = os.path.getsize(OUT)
    print(f"{OUT}: {size / 1e6:.2f} MB, {len(names)} files "
          f"({len(items)} item definitions, {len(models)} models, {len(pngs)} textures, {len(metas)} animations)")
    for n in names:
        if "/" not in n:
            print("  root:", n)


if __name__ == "__main__":
    main()
