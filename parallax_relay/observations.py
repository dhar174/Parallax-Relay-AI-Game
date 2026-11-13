"""The sole engine-to-agent observation boundary."""
import json
from .protocol import Observation
from .state import WorldState, public_hud
from .render import render_png


def observe(world: WorldState, role: str) -> Observation:
    hud = public_hud(world, role)  # Explicit allowlist, never snapshot().
    return Observation(role, world.turn, json.dumps(hud, sort_keys=True), render_png(world, role))
