"""Read the CLI record format for the workbench."""
import base64
import json
from pathlib import Path


def read_run(directory: Path) -> dict:
    """Read the CLI's native spectator files for fixture or companion output."""
    data = {}
    for name in ("manifest", "result", "final_state"):
        data[name] = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    for name in ("calls", "phases", "replay"):
        lines = (directory / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        data[name] = [json.loads(line) for line in lines if line.strip()]
    data["images"] = {
        path.name: "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        for path in sorted(directory.glob("*.png"))
    }
    return data
