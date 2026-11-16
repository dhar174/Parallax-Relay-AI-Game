"""Print installed distribution versions and supplied license texts as JSON.

Run with the target environment's Python. This is offline metadata collection,
not advisory scanning or legal clearance. No environment variables, direct URLs,
or arbitrary distribution metadata are collected.
"""

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import platform
import sys


def collect_inventory(paths=None):
    """Collect all installed distributions, retaining missing license evidence."""
    packages = []
    for distribution in metadata.distributions(path=sys.path if paths is None else paths):
        info = distribution.metadata
        licenses = []
        for entry in distribution.files or []:
            # Wheel license data lives in dist-info, not importable application code.
            if not entry.parts or not entry.parts[0].endswith((".dist-info", ".egg-info")):
                continue
            name = entry.name.lower()
            if not ("licenses" in entry.parts[1:] or
                    name.startswith(("license", "copying", "notice"))):
                continue
            content = distribution.locate_file(entry).read_bytes()
            try:
                license_text = content.decode("utf-8")
                text_error = None
            except UnicodeDecodeError:
                license_text = None
                text_error = "not UTF-8"
            licenses.append({"path": str(entry),
                             "sha256": hashlib.sha256(content).hexdigest(),
                             "text": license_text, "text_error": text_error})
        packages.append({"name": info["Name"], "version": distribution.version,
                         "license_expression": info.get("License-Expression"),
                         "license_metadata": info.get("License"),
                         "license_classifiers": [c for c in info.get_all("Classifier", [])
                                                 if c.startswith("License ::")],
                         "license_files": sorted(licenses, key=lambda item: item["path"])})
    return {"collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "architecture": platform.machine(),
            "packages": sorted(packages, key=lambda item: item["name"].lower())}


if __name__ == "__main__":
    print(json.dumps(collect_inventory(), indent=2, ensure_ascii=False))
