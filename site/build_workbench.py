"""Build static assets and a portable offline companion from this checkout."""
import json
from pathlib import Path
import shutil
import stat
import sys
import zipfile

from run_records import read_run
from runtime_contract import checkout_source, runtime_fingerprint

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
OUTPUT = ROOT / "build" / "workbench" / "dist"
sys.path.insert(0, str(ROOT))

from parallax_relay.config import GameConfig, load_config
from parallax_relay.state import PRIVATE_GOALS
from scripts.live_smoke import load_profile


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n",
                    encoding="utf-8")


def build(output: Path = OUTPUT) -> Path:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(SITE / "web", output)
    source = checkout_source(ROOT)
    contract = {
        "commit": source["revision"] or "unavailable",
        "source_status": source["status"],
        "runtime_fingerprint": runtime_fingerprint(ROOT),
        "schema": GameConfig.model_json_schema(),
        "defaults": load_config(ROOT / "configs" / "three_models.toml").model_dump(),
        "goals": PRIVATE_GOALS,
        "live_smoke": load_profile(ROOT / "configs" / "live_smoke.json"),
    }
    write_json(output / "contract.json", contract)
    write_json(output / "fixture.json", read_run(ROOT / "example_run"))
    shutil.copytree(ROOT / "example_run", output / "example_run")
    shutil.copyfile(ROOT / "LICENSE", output / "UPSTREAM_LICENSE.txt")

    with zipfile.ZipFile(output / "relay-workbench.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path: Path, name: str) -> None:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
        for name in ("relay_workbench.py", "runtime_contract.py", "run_records.py"):
            add(SITE / name, f"relay-workbench/{name}")
        add(ROOT / "docs" / "WORKBENCH.md", "relay-workbench/README.md")
        add(ROOT / "LICENSE", "relay-workbench/LICENSE")
        for path in sorted(output.rglob("*"), key=lambda path: path.relative_to(output).as_posix()):
            if path.is_file() and path.name != "relay-workbench.zip":
                relative = path.relative_to(output).as_posix()
                add(path, f"relay-workbench/site/{relative}")
    return output


if __name__ == "__main__":
    print(build())
