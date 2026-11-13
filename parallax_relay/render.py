"""Render each sensor view from shared world state, without text-state leakage.

These images are real PNGs suitable for multimodal models. All views use
identical coordinate geometry. This is prototype art, not final production art.
"""

from __future__ import annotations

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .state import WorldState, WIDTH, GAP, ARTIFACT, ENERGY_CELL, EXIT, MOTOR

W, H, DX, X0 = 850, 295, 58, 76
FLOOR_Y = 220
COLORS = {"SPECTRA": "#6EB3FA", "PYRA": "#F89C65", "FLUX": "#72DBCB", "ECHO": "#C2ABF9"}


def px(x: int) -> int:
    return X0 + x * DX


def render_png(world: WorldState, sensor: str) -> bytes:
    """Return PNG bytes. sensor: SPECTRA/PYRA/FLUX/ECHO/SPECTATOR."""
    if sensor not in {"SPECTRA", "PYRA", "FLUX", "ECHO", "SPECTATOR"}:
        raise ValueError(f"Invalid sensor: {sensor}")
    img = Image.new("RGB", (W, H), "#101925")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 12)
    except OSError:
        f = ImageFont.load_default()
    d.text((28, 20), "PARALLAX RELAY  /  SPLIT SPAN", fill="#E2EDFA", font=f)
    d.text((28, 42), "SENSOR: " + sensor + "  |  TURN " + str(world.turn), fill=COLORS.get(sensor, "#CDE6F4"), font=f)
    for x in range(WIDTH):
        cx = px(x)
        d.line((cx, 65, cx, 238), fill="#263447", width=1)
        d.text((cx - 3, 243), str(x), fill="#8C9BAD", font=f)
        if x not in GAP or world.bridge_extended:
            if x in GAP:
                fill = "#467F77" if sensor in {"FLUX", "SPECTATOR"} else "#52677A"
            else:
                fill = "#3E4C5D"
            d.rectangle((cx - DX//2 + 1, FLOOR_Y, cx + DX//2 - 1, FLOOR_Y + 16), fill=fill)
    # Common geometry is outlined for positional fairness, but overlays differ.
    d.rectangle((px(MOTOR)-10, FLOOR_Y-31, px(MOTOR)+10, FLOOR_Y-1), outline="#72859C", width=2)
    d.rectangle((px(EXIT)-17, FLOOR_Y-91, px(EXIT)+17, FLOOR_Y-1), outline="#788699", width=2)
    if sensor in {"SPECTRA", "SPECTATOR"}:
        d.rectangle((px(MOTOR)-8, FLOOR_Y-29, px(MOTOR)+8, FLOOR_Y-17), fill="#A9CFEE")
        if not world.shard_collected:
            x, y = px(ARTIFACT), FLOOR_Y-47
            d.polygon([(x,y-14),(x+12,y),(x,y+14),(x-12,y)], fill="#E1ABF5")
            d.text((x-25, y-30), "SHARD", fill="#EFC9FF", font=f)
        d.text((px(EXIT)-20,FLOOR_Y-110), "EXIT", fill="#BDD3E8", font=f)
        d.text((px(MOTOR)-25,FLOOR_Y-51), "CONSOLE", fill="#BDD3E8", font=f)
    if sensor in {"PYRA", "SPECTATOR"}:
        heat = world.motor_heat
        x, y = px(MOTOR), FLOOR_Y-10
        # Radii and color reflect the simulated heat state.
        r = 14 + heat * 5
        d.ellipse((x-r,y-r,x+r,y+r), outline="#C85F41", width=2)
        d.ellipse((x-12,y-12,x+12,y+12), fill="#E46B3F" if heat >= 3 else "#B59E57")
        d.text((x-36, y-r-15), f"HEAT {heat}", fill="#F6A16B", font=f)
    if sensor in {"FLUX", "SPECTATOR"}:
        d.line((px(MOTOR),FLOOR_Y+26,px(6),FLOOR_Y+26),fill="#72DBCB",width=3)
        d.line((px(6),FLOOR_Y+26,px(EXIT),FLOOR_Y+26),fill="#B5A66C",width=2)
        d.text((px(6)-26,FLOOR_Y+33), "BRIDGE FEED", fill="#78E7D7", font=f)
        if not world.cell_collected:
            x, y = px(ENERGY_CELL), FLOOR_Y-48
            d.rounded_rectangle((x-11,y-13,x+11,y+13), radius=4,fill="#42D5BB")
            d.text((x-14,y-31), "CELL", fill="#A6FFE9", font=f)
    if sensor == "ECHO":
        d.line((px(5),FLOOR_Y-9,px(7),FLOOR_Y-9), fill="#C2ABF9",width=3)
        d.text((px(5)-16,FLOOR_Y-34), "PAST SPAN",fill="#D6C8FC",font=f)
        for x in (6, 7):
            d.rectangle((px(x)-10,FLOOR_Y-51,px(x)+10,FLOOR_Y-31),outline="#9A80C2",width=2)
    # Visible robot coordinates are shared; robot identity is not hidden.
    for role, robot in world.robots.items():
        x = px(robot.x)
        # Allow colocated robots to remain visible, by slight role offsets.
        offset = {"SPECTRA":-12, "PYRA":0,"FLUX":12,"ECHO":20}.get(role,0)
        d.rounded_rectangle((x-11+offset,FLOOR_Y-28,x+10+offset,FLOOR_Y-8),radius=4,fill=COLORS.get(role,"#FFFFFF"))
        d.text((x-7+offset,FLOOR_Y-49),role[0],fill="#D4E0E9",font=f)
    if world.exit_unlocked:
        d.rectangle((px(EXIT)-12,FLOOR_Y-85,px(EXIT)+12,FLOOR_Y-1),fill="#1E806E")
    if sensor == "SPECTATOR":
        d.text((28,H-24),f"Energy {world.energy} | Coolant {world.coolant} | Heat {world.motor_heat} | Bridge {world.bridge_extended} | Exit {world.exit_unlocked}",fill="#E2EDFA",font=f)
    else:
        d.text((28,H-24),"Images carry sensor-specific facts. Public text HUD is sent separately.",fill="#8F9EAD",font=f)
    b = BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()
