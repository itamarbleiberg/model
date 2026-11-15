"""The five Time Blade variants: palettes, energy colours and animation timing."""


def hexpal(*cols):
    out = []
    for c in cols:
        c = c.lstrip("#")
        out.append(tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)))
    return out


COPPER = hexpal("#1a0d08", "#2f170d", "#472313", "#62311a", "#7e4223", "#9b552e", "#b56b3b",
                "#cc834b", "#e0a166", "#f0c08b", "#fbe1bf")
BRONZE = hexpal("#180e07", "#2b1a0d", "#412813", "#583919", "#704a21", "#8a5e2b", "#a37538",
                "#b98d4b", "#cda765", "#e0c38c", "#f2e1bd")
SILVER = hexpal("#14171a", "#23282d", "#353c43", "#4a535c", "#626c76", "#7c8792", "#97a2ad",
                "#b2bcc6", "#ccd4dc", "#e5eaef", "#fbfdff")
GREEN = hexpal("#03170a", "#062b12", "#0a441c", "#0f6227", "#178334", "#22a743", "#3cc957",
               "#6be37a", "#a8f5a8", "#e2ffe0", "#ffffff")
BLUE = hexpal("#030b1f", "#061736", "#0a2552", "#103773", "#184c96", "#2365bb", "#3784dc",
              "#5ea7f2", "#97cdfb", "#d6edff", "#ffffff")
RED = hexpal("#1a0202", "#300404", "#4c0707", "#6b0b0b", "#8e1010", "#b31616", "#d3221c",
             "#ec3c2c", "#ff6a4e", "#ffb39a", "#fff1ea")
AMBER = hexpal("#1e0d02", "#361704", "#552507", "#76350a", "#9a4a0d", "#be6111", "#dd7d1a",
               "#f39b2f", "#ffbd5e", "#ffe0a8", "#fffbe8")

# frames: blade texture frames / energy (lightning) frames
VARIANTS = {
    "basic": dict(
        id="basic_time_blade", title="Basic Time Blade", title_he="להב זמן בסיסי",
        text_color="gold", body=BRONZE, crown=COPPER, cuff=COPPER, blade=SILVER, metal_blade=True,
        glow=(1.0, 0.76, 0.24), spark_core=(1.0, 0.97, 0.80), spark_glow=(1.0, 0.72, 0.18),
        body_glow=0.14, flow=1, flow_speed=1.0, bolt_density=0.55,
        blade_frames=16, blade_frametime=3, energy_frames=12, energy_frametime=2,
        lore="Bronze, copper and silver. Golden time energy.",
    ),
    "forward": dict(
        id="forward_time_blade", title="Forward Time Blade", title_he="להב הזמן קדימה",
        text_color="green", body=COPPER, crown=COPPER, cuff=COPPER, blade=GREEN, metal_blade=False,
        glow=(0.30, 1.0, 0.38), spark_core=(0.90, 1.0, 0.90), spark_glow=(0.30, 1.0, 0.40),
        body_glow=0.5, flow=1, flow_speed=1.0, bolt_density=1.0,
        blade_frames=16, blade_frametime=1, energy_frames=12, energy_frametime=1,
        lore="Speeds time up. Energy races to the tips.",
    ),
    "slowmo": dict(
        id="slowmo_time_blade", title="Slow-Mo Time Blade", title_he="להב הזמן האיטי",
        text_color="blue", body=COPPER, crown=COPPER, cuff=COPPER, blade=BLUE, metal_blade=False,
        glow=(0.30, 0.62, 1.0), spark_core=(0.88, 0.95, 1.0), spark_glow=(0.32, 0.62, 1.0),
        body_glow=0.5, flow=1, flow_speed=0.5, bolt_density=0.85,
        blade_frames=16, blade_frametime=5, energy_frames=12, energy_frametime=4,
        lore="Slows time to a crawl. Lazy lightning.",
    ),
    "pause": dict(
        id="pause_time_blade", title="Pause Time Blade", title_he="להב עצירת הזמן",
        text_color="red", body=COPPER, crown=COPPER, cuff=COPPER, blade=RED, metal_blade=False,
        glow=(1.0, 0.24, 0.20), spark_core=(1.0, 0.88, 0.85), spark_glow=(1.0, 0.22, 0.18),
        body_glow=0.5, flow=0, flow_speed=0.0, bolt_density=0.9,
        blade_frames=16, blade_frametime=1, energy_frames=12, energy_frametime=2,
        lore="Freezes time. Its energy stutters and halts.",
    ),
    "reversal": dict(
        id="reversal_time_blade", title="Reversal Time Blade", title_he="להב היפוך הזמן",
        text_color="gold", text_hex="#FF9A1F", body=COPPER, crown=COPPER, cuff=COPPER, blade=AMBER,
        metal_blade=False,
        glow=(1.0, 0.56, 0.12), spark_core=(1.0, 0.94, 0.80), spark_glow=(1.0, 0.55, 0.10),
        body_glow=0.5, flow=-1, flow_speed=1.0, bolt_density=0.95,
        blade_frames=16, blade_frametime=2, energy_frames=12, energy_frametime=2,
        lore="Turns time back. Energy flows to the hilt.",
    ),
}
ORDER = ["basic", "forward", "slowmo", "pause", "reversal"]


def blade_mcmeta(v):
    if v["flow"] == 0:
        # Pause: a heartbeat pulse, then the energy freezes for over a second
        frames = [{"index": 0, "time": 26}] + list(range(1, v["blade_frames"]))
        return {"animation": {"interpolate": False, "frametime": v["blade_frametime"], "frames": frames}}
    return {"animation": {"interpolate": False, "frametime": v["blade_frametime"]}}


def energy_mcmeta(v):
    n = v["energy_frames"]
    if v["flow"] == 0:
        # stop-and-go crackle: some frames freeze
        frames = []
        for i in range(n):
            frames.append({"index": i, "time": 9} if i % 4 == 0 else i)
        return {"animation": {"interpolate": False, "frametime": v["energy_frametime"], "frames": frames}}
    if v["flow"] < 0:
        # reversal: the crackle literally plays backwards
        return {"animation": {"interpolate": False, "frametime": v["energy_frametime"],
                              "frames": list(range(n - 1, -1, -1))}}
    return {"animation": {"interpolate": False, "frametime": v["energy_frametime"]}}
