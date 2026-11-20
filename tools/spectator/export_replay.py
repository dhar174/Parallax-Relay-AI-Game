"""Export a native recording to a portable, offline spectator viewer."""

import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))
from run_records import read_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="Native recording directory")
    parser.add_argument("--out", type=Path, required=True, help="Fresh export directory")
    args = parser.parse_args()

    try:
        source = args.recording.resolve(strict=True)
        destination = args.out.resolve()
        if destination == source or source in destination.parents:
            raise ValueError("Export directory must be outside the recording")
        data = read_run(source)
        data["records"] = data.pop("replay")
        artwork = Path(__file__).with_name("artwork") / "light-review"
        names = ("room-background", "floor", "bridge", "motor-console", "memory-shard",
                 "energy-cell", "exit-closed", "exit-open", "spectra-idle", "pyra-idle", "flux-idle")
        data["artwork"] = {
            name: "data:image/png;base64," + base64.b64encode((artwork / (name + ".png")).read_bytes()).decode("ascii")
            for name in names
        }
        encoded = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
        if template.count("__REPLAY_DATA__") != 1:
            raise ValueError("Invalid spectator viewer template")
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "index.html").write_text(template.replace("__REPLAY_DATA__", encoded), encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Could not export replay: {error}", file=sys.stderr)
        return 1
    print(f"Spectator replay: {destination / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
