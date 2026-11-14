"""Run a scripted complete game and save PNG observations plus JSONL replay.

Usage: python -m parallax_relay.demo [--out NEW_DIRECTORY]

Omitting --out creates a unique directory under runs/. Existing paths are rejected.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4
from .engine import resolve_turn, score
from .state import initial_world, public_hud
from .scripted import PLAN, FIRST_BROADCAST
from .render import render_png


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    world = initial_world()
    records = []
    for idx, actions in enumerate(PLAN):
        # In a real match, messages would be returned by async model calls.
        messages = FIRST_BROADCAST if idx == 0 else {
            role: f"Turn {idx + 1}: proposing {action.kind.lower()} as planned."
            for role, action in actions.items()
        }
        observations = {}
        for role in world.robots:
            image_name = f"turn_{idx:02d}_{role.lower()}.png"
            (out/image_name).write_bytes(render_png(world, role))
            observations[role] = {
                "image": image_name,
                "hud": public_hud(world, role),
            }
        (out/f"turn_{idx:02d}_spectator.png").write_bytes(render_png(world,"SPECTATOR"))
        after = resolve_turn(world, actions)
        records.append({
            "turn": idx + 1,
            "observations": observations,
            "messages": messages,
            "sealed_actions": {r: asdict(a) for r,a in actions.items()},
            "events": after.events,
            "state_after": after.snapshot(),  # PRIVILEGED replay only, never agent input
        })
        world = after
        print(f"Round {world.turn}: " + "; ".join(world.events))
        if world.win or world.loss:
            break
    (out/"replay.jsonl").write_text(
        "\n".join(json.dumps(rec) for rec in records) + "\n", encoding="utf-8")
    result = {"win":world.win,"turns":world.turn,"scores":score(world), "energy":world.energy}
    (out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    save_replay_viewer(out, records)
    print("\nRESULT:",json.dumps(result,indent=2))
    return result


def save_replay_viewer(out: Path, records: list[dict]) -> None:
    """Offline static viewer: no network, server, API key, or JS build required."""
    viewer = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Parallax Relay — The Split Span</title>
<style>
:root{color-scheme:dark;font-family:system-ui,Segoe UI,sans-serif;background:#0c121c;color:#ecf3f9}
*{box-sizing:border-box}body{margin:0;padding:24px;max-width:1460px;margin:auto}
h1{font-size:28px;margin:0 0 4px}p{color:#aebed0;margin:6px 0 18px}
header{display:flex;justify-content:space-between;align-items:end;flex-wrap:wrap;gap:14px;margin-bottom:18px}
input{width:min(400px,70vw);accent-color:#7dc2f3}strong{color:#f3db91}
.sensors{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:14px}
.panel,.log{background:#141f2c;border:1px solid #334359;border-radius:12px;padding:13px}
.panel h2{font-size:15px;margin:0 0 10px;color:#bcd2e8}
.panel img{width:100%;border-radius:6px;display:block;image-rendering:auto}
.logs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.log h2{font-size:15px}.log div{line-height:1.55;margin:8px 0;font-size:14px}
.label{font-weight:650;color:#9dd5ed}footer{color:#8ea5bb;margin:20px 0;font-size:13px}
@media(max-width:800px){.sensors,.logs{grid-template-columns:1fr}body{padding:14px}}
</style></head>
<body><header><div><h1>PARALLAX RELAY</h1><p>The Split Span · deterministic scripted replay · not live LLM gameplay</p></div>
<div><label for="round">Round <strong id="num">1</strong> / <span id="total"></span></label><br><input id="round" type="range" min="0" max="0" value="0"></div></header>
<div class="sensors">
<section class="panel"><h2>SPECTRA · Optical</h2><img id="SPECTRA" alt="Optical robot view"></section>
<section class="panel"><h2>PYRA · Thermal</h2><img id="PYRA" alt="Thermal robot view"></section>
<section class="panel"><h2>FLUX · Electromagnetic</h2><img id="FLUX" alt="Electromagnetic robot view"></section>
<section class="panel"><h2>SPECTATOR · Omniscient</h2><img id="SPECTATOR" alt="Full game view"></section>
</div><div class="logs"><section class="log"><h2>Communications and committed actions</h2><div id="messages"></div></section>
<section class="log"><h2>Engine events</h2><div id="events"></div></section></div>
<footer>Game state resolves actions in the fixed sequence: controls → movement → collection / exit → victory.
The spectator feed is privileged and must never be sent to an agent.</footer>
<script>
const records=__REPLAY_DATA__;
const slider=document.getElementById('round');slider.max=records.length-1;
document.getElementById('total').textContent=records.length;
function line(parent,label,value){const el=document.createElement('div');const key=document.createElement('span');key.className='label';key.textContent=label+' ';el.append(key,document.createTextNode(value));parent.append(el)}
function draw(){const i=Number(slider.value),r=records[i];document.getElementById('num').textContent=i+1;
for(const role of ['SPECTRA','PYRA','FLUX'])document.getElementById(role).src=r.observations[role].image;
document.getElementById('SPECTATOR').src='turn_'+String(i).padStart(2,'0')+'_spectator.png';
const m=document.getElementById('messages');m.replaceChildren();
for(const [role,message] of Object.entries(r.messages))line(m,role+':',message);
for(const [role,action] of Object.entries(r.sealed_actions))line(m,role+' action:',action.kind+(action.kind==='MOVE'?' '+(action.direction>0?'+':'')+action.direction+' × '+action.steps:''));
const e=document.getElementById('events');e.replaceChildren();for(const event of r.events)line(e,'•',event)
}slider.addEventListener('input',draw);draw();
</script></body></html>"""
    html = viewer.replace("__REPLAY_DATA__", json.dumps(records).replace("</", "<\\/"))
    (out/"index.html").write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Run the offline scripted legacy demo.')
    p.add_argument('--out', type=Path,
                   help='New output directory; defaults to a unique directory under runs/. Existing paths are rejected.')
    args = p.parse_args(argv)
    out = args.out or Path('runs') / (
        'demo_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:6])
    try:
        run(out)
    except FileExistsError:
        # Windows also raises EEXIST when a parent component is a regular file.
        try:
            out.lstat()
        except OSError:
            print('Local file operation failed. Check paths and permissions.', file=sys.stderr)
        else:
            print('Output path already exists. Choose a new --out path.', file=sys.stderr)
        return 2
    except OSError:
        print('Local file operation failed. Check paths and permissions.', file=sys.stderr)
        return 2
    print(f'Replay: {out / "index.html"}')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
