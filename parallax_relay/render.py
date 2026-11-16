"""Role-specific PNG projections. Full room identity is never a player label."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .state import WorldState

W,H,DX,X0=850,295,58,76
FLOOR_Y=220
COLORS={"SPECTRA":"#6EB3FA","PYRA":"#F89C65","FLUX":"#72DBCB","ECHO":"#C2ABF9"}

def px(x: int) -> int:
    return X0+x*DX


def render_png(world: WorldState,sensor: str) -> bytes:
    if sensor not in {*COLORS,"SPECTATOR"}:raise ValueError(f"Invalid sensor: {sensor}")
    room=world.room;gaps={x for b in room.bridges for x in b.gap}
    image=Image.new("RGB",(W,H),"#101925");draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype("DejaVuSans.ttf",12)
    except OSError:font=ImageFont.load_default()
    draw.text((28,20),"PARALLAX RELAY  /  COOPERATIVE ROOM",fill="#E2EDFA",font=font)
    draw.text((28,42),"SENSOR: "+sensor+"  |  TURN "+str(world.turn),fill=COLORS.get(sensor,"#CDE6F4"),font=font)
    for x in range(room.width):
        cx=px(x);draw.line((cx,65,cx,238),fill="#263447",width=1)
        draw.text((cx-3,243),str(x),fill="#8C9BAD",font=font)
        powered=any(x in b.gap and f"bridge_{i}" in world.powered_bridges for i,b in enumerate(room.bridges))
        if x not in gaps or powered:
            color="#3E4C5D" if x not in gaps else "#467F77" if sensor in {"FLUX","SPECTATOR"} else "#52677A"
            draw.rectangle((cx-DX//2+1,FLOOR_Y,cx+DX//2-1,FLOOR_Y+16),fill=color)
    draw.rectangle((px(room.exit)-17,FLOOR_Y-91,px(room.exit)+17,FLOOR_Y-1),outline="#788699",width=2)
    for i,bridge in enumerate(room.bridges):
        x=px(bridge.motor)
        draw.rectangle((x-10,FLOOR_Y-31,x+10,FLOOR_Y-1),outline="#72859C",width=2)
        if sensor in {"SPECTRA","SPECTATOR"}:
            draw.rectangle((x-8,FLOOR_Y-29,x+8,FLOOR_Y-17),fill="#A9CFEE")
            draw.text((x-25,FLOOR_Y-51),"CONSOLE",fill="#BDD3E8",font=font)
        if sensor in {"PYRA","SPECTATOR"}:
            heat=world.motor_heats[f"bridge_{i}"];y=FLOOR_Y-10;r=14+heat*5
            draw.ellipse((x-r,y-r,x+r,y+r),outline="#C85F41",width=2)
            draw.ellipse((x-12,y-12,x+12,y+12),fill="#E46B3F" if heat>=3 else "#B59E57")
            draw.text((x-36,y-r-15),f"HEAT {heat}",fill="#F6A16B",font=font)
        if sensor in {"FLUX","SPECTATOR"}:
            center=px(sum(bridge.gap)/len(bridge.gap))
            draw.line((x,FLOOR_Y+26,center,FLOOR_Y+26),fill="#72DBCB",width=3)
            draw.text((center-26,FLOOR_Y+33),"FEED",fill="#78E7D7",font=font)
    if sensor in {"SPECTRA","SPECTATOR"}:
        if not world.shard_collected:
            x,y=px(room.shard),FLOOR_Y-47
            draw.polygon([(x,y-14),(x+12,y),(x,y+14),(x-12,y)],fill="#E1ABF5")
            draw.text((x-25,y-30),"SHARD",fill="#EFC9FF",font=font)
        draw.text((px(room.exit)-20,FLOOR_Y-110),"EXIT",fill="#BDD3E8",font=font)
    if sensor in {"FLUX","SPECTATOR"}:
        for cell in room.cells:
            if cell in world.collected_cells:continue
            x,y=px(cell),FLOOR_Y-48
            draw.rounded_rectangle((x-11,y-13,x+11,y+13),radius=4,fill="#42D5BB")
            draw.text((x-14,y-31),"CELL",fill="#A6FFE9",font=font)
    if sensor=="ECHO":
        first=room.bridges[0].gap
        draw.line((px(min(first)),FLOOR_Y-9,px(max(first)),FLOOR_Y-9),fill="#C2ABF9",width=3)
        draw.text((px(min(first))-16,FLOOR_Y-34),"PAST SPAN",fill="#D6C8FC",font=font)
    for role,robot in world.robots.items():
        x=px(robot.x);offset={"SPECTRA":-12,"PYRA":0,"FLUX":12,"ECHO":20}.get(role,0)
        draw.rounded_rectangle((x-11+offset,FLOOR_Y-28,x+10+offset,FLOOR_Y-8),radius=4,fill=COLORS.get(role,"#FFFFFF"))
        draw.text((x-7+offset,FLOOR_Y-49),role[0],fill="#D4E0E9",font=font)
    if world.exit_unlocked:draw.rectangle((px(room.exit)-12,FLOOR_Y-85,px(room.exit)+12,FLOOR_Y-1),fill="#1E806E")
    if sensor=="SPECTATOR":
        heat="/".join(map(str,world.motor_heats.values()));bridges="/".join("on" if key in world.powered_bridges else "off" for key in world.motor_heats)
        footer=f"Energy {world.energy} | Coolant {world.coolant} | Heat {heat} | Bridges {bridges} | Exit {world.exit_unlocked}"
    else:footer="Images carry sensor-specific facts. Public text HUD is sent separately."
    draw.text((28,H-24),footer,fill="#8F9EAD",font=font)
    output=BytesIO();image.save(output,format="PNG");return output.getvalue()
