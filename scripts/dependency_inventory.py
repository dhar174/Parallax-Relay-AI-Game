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
from pathlib import Path, PurePosixPath, PureWindowsPath


def collect_license_file(root, entry):
    """Read only a confined license path; never include OS exception details."""
    result = {"path": str(entry), "sha256": None, "text": None, "text_error": None}
    try:
        if (entry.is_absolute() or PureWindowsPath(str(entry)).drive or
                "\\" in str(entry) or ".." in entry.parts or
                not entry.parts or entry.parts[0] != root.name or
                any(part.casefold() == "direct_url.json" for part in entry.parts)):
            result["text_error"] = "rejected unsafe license path"
            return result
        relative = entry.parts[1:]
        if not relative:
            result["text_error"] = "rejected unsafe license path"
            return result
        area = root / "licenses" if relative[0] == "licenses" else root
        if area == root and (len(relative) != 1 or not relative[0].lower().startswith(
                ("license", "copying", "notice"))):
            result["text_error"] = "rejected unsafe license path"
            return result
        resolved = root.joinpath(*relative).resolve()
        if (not resolved.is_relative_to(area) or
                resolved.name.casefold() == "direct_url.json"):
            result["text_error"] = "rejected unsafe license path"
            return result
        # Reject hard-link aliases too, without reading private installation data.
        direct_url = root / "direct_url.json"
        if direct_url.exists() and resolved.samefile(direct_url):
            result["text_error"] = "rejected private metadata alias"
            return result
        content = resolved.read_bytes()
        result["sha256"] = hashlib.sha256(content).hexdigest()
        try:
            result["text"] = content.decode("utf-8")
        except UnicodeDecodeError:
            result["text_error"] = "not UTF-8"
    except (OSError, RuntimeError) as error:
        result["text_error"] = type(error).__name__
    return result


def collect_inventory(paths=None):
    """Collect all installed distributions, retaining missing license evidence."""
    packages = []
    for distribution in metadata.distributions(path=sys.path if paths is None else paths):
        info = distribution.metadata
        licenses = []
        files = distribution.files
        # PathDistribution has no public metadata-directory accessor. Its _path
        # identifies this distribution's own dist-info/egg-info, independently of RECORD.
        root = Path(distribution._path).resolve()
        candidates = set()
        for entry in files or []:
            # Wheel license data lives in dist-info, not importable application code.
            if not entry.parts or not entry.parts[0].endswith((".dist-info", ".egg-info")):
                continue
            name = entry.name.lower()
            if not ("licenses" in entry.parts[1:] or
                    name.startswith(("license", "copying", "notice"))):
                continue
            candidates.add(PurePosixPath(entry))
        # PEP 639 declarations remain evidence even when RECORD is missing or
        # omits a declared file. Older wheel layouts may store notices at root.
        declared = info.get_all("License-File", [])
        modern_layout = (info.get("Metadata-Version", "") in ("2.4", "2.5") or
                         (root / "licenses").is_dir())
        for name in declared:
            candidates.add(PurePosixPath(root.name, "licenses", name) if modern_layout
                           else PurePosixPath(root.name, name))
        for entry in candidates:
            licenses.append(collect_license_file(root, entry))
        packages.append({"name": info["Name"], "version": distribution.version,
                         "license_expression": info.get("License-Expression"),
                         "license_metadata": info.get("License"),
                         "license_classifiers": [c for c in info.get_all("Classifier", [])
                                                 if c.startswith("License ::")],
                         "file_inventory_available": files is not None,
                         "declared_license_files": declared,
                         "license_files": sorted(licenses, key=lambda item: item["path"])})
    return {"collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "architecture": platform.machine(),
            "packages": sorted(packages, key=lambda item: item["name"].lower())}


if __name__ == "__main__":
    print(json.dumps(collect_inventory(), indent=2, ensure_ascii=False))
