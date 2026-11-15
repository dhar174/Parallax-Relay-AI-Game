"""Identify the checkout inputs shared by the Python CLI and workbench."""
import hashlib
import os
from pathlib import Path
import re
import subprocess


def checkout_revision(root: Path) -> str:
    return checkout_source(root)["revision"] or "unavailable"


def checkout_source(root: Path) -> dict:
    """Identify this project root without trusting parent repos or Git overrides."""
    source = {"revision": None, "status": "unavailable"}
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=", "-C", str(root), *args], env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1,
        )
    try:
        identity = git("rev-parse", "--show-toplevel", "HEAD")
        lines = identity.stdout.splitlines()
        if identity.returncode or len(lines) != 2 or Path(lines[0]).resolve() != root.resolve():
            return source
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", lines[1]):
            return source
        source["revision"] = lines[1]
        status = git("status", "--porcelain=v1", "--untracked-files=normal")
        if status.returncode == 0:
            source["status"] = "dirty" if status.stdout else "clean"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return source


def runtime_fingerprint(root: Path) -> str:
    """Accept later checkouts when their runtime inputs are byte-equivalent.

    Normalize line endings so the same revision works with Git autocrlf.
    Ignore generated Python caches and include the default configuration.
    """
    files = [root / "configs" / "three_models.toml"]
    files.extend(
        path for path in (root / "parallax_relay").rglob("*")
        if path.is_file() and path.suffix in {".py", ".html"}
    )
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest())
    return digest.hexdigest()
