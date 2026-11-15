"""Simulates how an item model is placed in the GUI, first person and third person
(transform chains copied from 1.21.11: ItemTransform.apply, ItemInHandRenderer,
ItemInHandLayer, HumanoidModel/ModelPart, LivingEntityRenderer).
"""
import math
import numpy as np
import mc
import render as rd
from mc import Rx, Ry, Rz, unit


class QuadSet:
    def __init__(self, P, UV, TI, N, light, emis_w, textures):
        self.P, self.UV, self.TI, self.N = P, UV, TI, N
        self.light, self.emis_w, self.textures = light, emis_w, textures

    @staticmethod
    def from_mesh(m):
        return QuadSet(m.P.copy(), m.UV.copy(), m.TI.copy(), m.N.copy(), m.light.copy(),
                       m.emis_w.copy(), list(m.textures))

    def transformed(self, M):
        P = self.P.reshape(-1, 3)
        P = (np.concatenate([P, np.ones((len(P), 1))], 1) @ M.T)[:, :3].reshape(self.P.shape)
        A = M[:3, :3]
        N = self.N @ np.linalg.inv(A)       # inverse transpose for normals
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        return QuadSet(P, self.UV, self.TI, N, self.light, self.emis_w, self.textures)

    @staticmethod
    def concat(sets):
        P, UV, TI, N, L, E, T = [], [], [], [], [], [], []
        off = 0
        for s in sets:
            P.append(s.P); UV.append(s.UV); TI.append(s.TI + off); N.append(s.N)
            L.append(s.light); E.append(s.emis_w); T += s.textures
            off += len(s.textures)
        return QuadSet(np.concatenate(P), np.concatenate(UV), np.concatenate(TI), np.concatenate(N),
                       np.concatenate(L), np.concatenate(E), T)


def solid_boxes(boxes):
    """boxes: list of (min_xyz, max_xyz, 4x4 matrix, rgb). Coordinates in final units."""
    P, UV, TI, N = [], [], [], []
    textures = []
    for (lo, hi, M, rgb) in boxes:
        tex = np.ones((2, 2, 4), np.float32)
        tex[..., :3] = rgb
        ti = len(textures)
        textures.append(tex)
        for f in mc.FACES:
            q = []
            for sel in mc.FACE_CORNERS[f]:
                q.append([hi[i] if sel[i] else lo[i] for i in range(3)])
            q = np.array(q, float)
            qh = np.concatenate([q, np.ones((4, 1))], 1) @ M.T
            P.append(qh[:, :3])
            UV.append(np.array([[0, 0], [0, 2], [2, 2], [2, 0]], float) * 0.5)
            TI.append(ti)
            N.append(np.array(mc.FACE_NORMAL[f], float))
    P = np.array(P); N = np.array(N)
    # normals as seen in final space
    out = QuadSet(P, np.array(UV), np.array(TI), N, np.zeros(len(P)), np.zeros(len(P)), textures)
    # transform normals by each box matrix (all boxes of one call share orientation per box)
    Ns = []
    k = 0
    for (lo, hi, M, rgb) in boxes:
        A = M[:3, :3]
        inv = np.linalg.inv(A)
        for _ in range(6):
            n = N[k] @ inv
            Ns.append(n / np.linalg.norm(n))
            k += 1
    out.N = np.array(Ns)
    return out


# ---------------------------------------------------------------- contexts
def gui_lights(side):
    L = rd.items_3d_lights() if side else rd.items_flat_lights()
    F = np.diag([1.0, -1.0, 1.0])            # game GUI space has y pointing down
    return (F @ L[0], F @ L[1])


def render_gui(mesh, display, px=64, side=False, bg=(0.545, 0.545, 0.545), clip=True):
    """Item in a 16x16 slot rendered at px x px (px/16 = GUI scale)."""
    qs = QuadSet.from_mesh(mesh).transformed(rd.item_transform(display, "gui"))
    V = np.eye(4)
    V[2, 3] = -10.0
    bgimg = np.ones((px, px, 3), np.float32) * np.array(bg, np.float32)
    img, cov = rd.rasterize(qs, V, px, px, proj=("ortho", 0.5), lights=gui_lights(side), bg=bgimg)
    return img


def first_person(mesh, display, W=960, H=540, left=False, equip=0.0, arm=True, bg=None):
    i = -1 if left else 1
    ctx = "firstperson_lefthand" if left else "firstperson_righthand"
    M = rd.T(i * 0.56, -0.52 + equip * -0.6, -0.72) @ rd.item_transform(display, ctx, left=left)
    qs = QuadSet.from_mesh(mesh).transformed(M)
    sets = [qs]
    if bg is None:
        bg = sky_bg(W, H)
    img, cov = rd.rasterize(QuadSet.concat(sets), np.eye(4), W, H, proj=("persp", 70.0),
                            lights=(rd.L0, rd.L1), bg=bg)
    return img


def sky_bg(W, H):
    y = np.linspace(0, 1, H)[:, None, None]
    top = np.array([0.47, 0.65, 1.0]); hor = np.array([0.75, 0.84, 1.0]); gr = np.array([0.36, 0.55, 0.25])
    sky = top * (1 - y / 0.55) + hor * (y / 0.55)
    img = np.where(y < 0.55, sky, gr * (1.1 - 0.3 * (y - 0.55)))
    return (img * np.ones((H, W, 3))).astype(np.float32)


# ---------------------------------------------------------------- third person
SKIN = (0.78, 0.6, 0.47)
SHIRT = (0.0, 0.66, 0.66)
PANTS = (0.18, 0.2, 0.55)
HAIR = (0.25, 0.17, 0.1)


def part_matrix(world, pivot, rot):
    """ModelPart.translateAndRotate: translate(pivot/16) then rotationZYX(z, y, x)."""
    rx, ry, rz = rot
    return world @ rd.T(*(np.array(pivot) / 16.0)) @ rd.R4(Rz(rz) @ Ry(ry) @ Rx(rx))


def player_world(body_yaw=0.0):
    return rd.R4(Ry(180.0 - body_yaw)) @ rd.S(-1, -1, 1) @ rd.S(0.9375) @ rd.T(0, -1.501, 0)


def player_boxes(W, right_arm_rot, left_arm_rot=(0, 0, 0)):
    px = 1 / 16.0

    def B(lo, hi, M, c):
        return (np.array(lo) * px, np.array(hi) * px, M, c)
    boxes = []
    head = part_matrix(W, (0, 0, 0), (0, 0, 0))
    boxes.append(B((-4, -8, -4), (4, 0, 4), head, SKIN))
    boxes.append(B((-4.2, -8.4, -4.2), (4.2, -6.5, 4.2), head, HAIR))
    body = part_matrix(W, (0, 0, 0), (0, 0, 0))
    boxes.append(B((-4, 0, -2), (4, 12, 2), body, SHIRT))
    ra = part_matrix(W, (-5, 2, 0), right_arm_rot)
    boxes.append(B((-3, -2, -2), (1, 6, 2), ra, SHIRT))
    boxes.append(B((-3, 6, -2), (1, 10, 2), ra, SKIN))
    la = part_matrix(W, (5, 2, 0), left_arm_rot)
    boxes.append(B((-1, -2, -2), (3, 6, 2), la, SHIRT))
    boxes.append(B((-1, 6, -2), (3, 10, 2), la, SKIN))
    for x in (-1.9, 1.9):
        lg = part_matrix(W, (x, 12, 0), (0, 0, 0))
        boxes.append(B((-2, 0, -2), (2, 12, 2), lg, PANTS))
    return solid_boxes(boxes)


def third_person(mesh, display, W=900, H=900, view="front", left=False, ground=True):
    Wm = player_world(0.0)
    arm_rot = (math.degrees(-math.pi / 10), 0, 0)    # holding an item: xRot = xRot * 0.5 - pi/10
    if left:
        right_rot, left_rot = (0, 0, 0), arm_rot
        pivot = (5, 2, 0)
    else:
        right_rot, left_rot = arm_rot, (0, 0, 0)
        pivot = (-5, 2, 0)
    sgn = -1 if left else 1
    hand = (part_matrix(Wm, pivot, left_rot if left else right_rot)
            @ rd.R4(Rx(-90.0)) @ rd.R4(Ry(180.0)) @ rd.T(sgn / 16.0, 0.125, -0.625))
    ctx = "thirdperson_lefthand" if left else "thirdperson_righthand"
    item = QuadSet.from_mesh(mesh).transformed(hand @ rd.item_transform(display, ctx, left=left))
    body = player_boxes(Wm, right_rot, left_rot)
    sets = [body, item]
    if view == "front":
        V = rd.look_at((-2.3, 1.75, 3.3), (-0.25, 1.05, 0.2))
    elif view == "side":
        V = rd.look_at((-4.0, 1.4, 0.4), (0.0, 1.0, 0.4))
    else:
        V = rd.look_at((-1.8, 2.3, -3.4), (-0.2, 1.1, 0.3))
    bg = sky_bg(W, H)
    img, cov = rd.rasterize(QuadSet.concat(sets), V, W, H, proj=("persp", 45.0),
                            lights=(V[:3, :3] @ rd.L0, V[:3, :3] @ rd.L1), bg=bg)
    return img
