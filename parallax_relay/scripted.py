"""Deterministic scripted agents for the first end-to-end smoke test.

These agents intentionally know the level solution. They are a test harness,
NOT a stand-in for LLM capability. Never send the full state to live agents.
"""

from .state import Action

# One action per role per round (turn is zero indexed here).
PLAN: list[dict[str, Action]] = [
    {
        "SPECTRA": Action("MOVE", direction=1, steps=2),
        "PYRA": Action("VENT"),
        "FLUX": Action("REROUTE"),
    },
    {
        "SPECTRA": Action("MOVE", direction=1, steps=2),
        "PYRA": Action("MOVE", direction=1, steps=2),
        "FLUX": Action("MOVE", direction=1, steps=2),
    },
    {
        "SPECTRA": Action("MOVE", direction=1, steps=2),
        "PYRA": Action("MOVE", direction=1, steps=2),
        "FLUX": Action("MOVE", direction=1, steps=2),
    },
    {
        "SPECTRA": Action("MOVE", direction=1, steps=1),
        "PYRA": Action("MOVE", direction=1, steps=2),
        "FLUX": Action("MOVE", direction=1, steps=2),
    },
    {
        "SPECTRA": Action("COLLECT"),
        "PYRA": Action("MOVE", direction=1, steps=2),
        "FLUX": Action("COLLECT"),
    },
    {
        "SPECTRA": Action("MOVE", direction=1, steps=2),
        "PYRA": Action("MOVE", direction=1, steps=1),
        "FLUX": Action("MOVE", direction=1, steps=2),
    },
    {
        "SPECTRA": Action("MOVE", direction=1, steps=1),
        "PYRA": Action("WAIT"),
        "FLUX": Action("UNLOCK"),
    },
]

FIRST_BROADCAST = {
    "SPECTRA": "I see a retracted bridge and an inscription. I'll approach the console, then look for artifacts.",
    "PYRA": "The motor is dangerously hot. I'll vent it before anyone energizes the bridge.",
    "FLUX": "The bridge feed needs 2 energy; I can reroute it this round. Let's coordinate.",
}
