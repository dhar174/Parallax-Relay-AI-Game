"""Build static assets and a portable offline companion from this checkout."""
import json
from pathlib import Path
import shutil
import sys
import zipfile

from run_records import read_run
from runtime_contract import checkout_revision, runtime_fingerprint

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
OUTPUT = ROOT / "build" / "workbench" / "dist"
sys.path.insert(0, str(ROOT))

from parallax_relay.config import GameConfig, load_config
from parallax_relay.state import PRIVATE_GOALS


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n",
                    encoding="utf-8")


def build(output: Path = OUTPUT) -> Path:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(SITE / "web", output)
    contract = {
        "commit": checkout_revision(ROOT),
        "runtime_fingerprint": runtime_fingerprint(ROOT),
        "schema": GameConfig.model_json_schema(),
        "defaults": load_config(ROOT / "configs" / "three_models.toml").model_dump(),
        "goals": PRIVATE_GOALS,
    }
    write_json(output / "contract.json", contract)
    write_json(output / "fixture.json", read_run(ROOT / "example_run"))
    shutil.copytree(ROOT / "example_run", output / "example_run")
    shutil.copyfile(ROOT / "LICENSE", output / "UPSTREAM_LICENSE.txt")

    with zipfile.ZipFile(output / "relay-workbench.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("relay_workbench.py", "runtime_contract.py", "run_records.py"):
            archive.write(SITE / name, f"relay-workbench/{name}")
        archive.write(ROOT / "docs" / "WORKBENCH.md", "relay-workbench/README.md")
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "relay-workbench.zip":
                relative = path.relative_to(output).as_posix()
                archive.write(path, f"relay-workbench/site/{relative}")
    return output


if __name__ == "__main__":
    print(build())
