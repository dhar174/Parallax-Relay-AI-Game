"""Read the CLI record format for the workbench."""
import base64
import json
from pathlib import Path
import re

RUN_IMAGE = re.compile(r"(?:turn_[0-9]+_(?:spectra|pyra|flux|spectator)|final_spectator)\.png")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_run(directory: Path) -> dict:
    """Read the CLI's native spectator files for fixture or companion output."""
    data = {}
    for name in ("manifest", "result", "final_state"):
        data[name] = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
        if not isinstance(data[name], dict):
            raise ValueError(f"Invalid {name}.json: expected an object")
    for name in ("calls", "phases", "replay"):
        lines = (directory / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        data[name] = [json.loads(line) for line in lines if line.strip()]
        if any(not isinstance(record, dict) for record in data[name]):
            raise ValueError(f"Invalid {name}.jsonl: expected object records")
    data["images"] = {}
    for path in sorted(directory.glob("*.png")):
        if not RUN_IMAGE.fullmatch(path.name):
            continue
        if path.is_symlink():
            raise ValueError("Run images must not be symbolic links")
        png = path.read_bytes()
        if not png.startswith(PNG_SIGNATURE):
            raise ValueError("Invalid PNG image")
        data["images"][path.name] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return data
