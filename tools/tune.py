"""Renders the in-hand / GUI contexts of a variant with the current display.json.

usage: tools/run.sh tools/tune.py VARIANT OUT.png
"""
import json
import os
import sys
import numpy as np
from PIL import Image

import render as rd
import handsim as hs
import preview as pv


def contexts(key, display=None, out=None):
    if display is None:
        display = json.load(open(os.path.join(os.path.dirname(__file__), "display.json")))
    elems = pv.load_geometry()
    tex, metas = pv.load_textures(key)
    mesh = pv.mesh_at(elems, tex)
    fp = rd.to_u8(hs.first_person(mesh, display, 960, 540))
    fpl = rd.to_u8(hs.first_person(mesh, display, 960, 540, left=True))
    tp = rd.to_u8(hs.third_person(mesh, display, 540, 540, view="front"))
    tps = rd.to_u8(hs.third_person(mesh, display, 540, 540, view="side"))
    tpb = rd.to_u8(hs.third_person(mesh, display, 540, 540, view="back"))
    gui_imgs = []
    for side in (False, True):
        for px in (16, 32, 64):
            g = rd.to_u8(hs.render_gui(mesh, display, px=px, side=side))
            g = np.kron(g, np.ones((128 // px, 128 // px, 1), np.uint8))
            gui_imgs.append(g)
    gui = np.concatenate(gui_imgs, 1)
    W = 960 * 2
    top = np.concatenate([fp, fpl], 1)
    mid = np.concatenate([tp, tps, tpb, np.zeros((540, W - 540 * 3, 3), np.uint8) + 40], 1)
    bot = np.zeros((128, W, 3), np.uint8) + 40
    bot[:, :gui.shape[1]] = gui
    img = np.concatenate([top, mid, bot], 0)
    Image.fromarray(img).save(out)


if __name__ == "__main__":
    contexts(sys.argv[1], out=sys.argv[2])
