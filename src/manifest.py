"""Run-manifest collection for reproducible CLI executions."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Iterable


def file_sha256(path: str | Path) -> str | None:
    """Return the SHA-256 hex digest for *path*, or ``None`` if unavailable."""
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_command(argv: Iterable[str]) -> str:
    """Format an argument vector as a command string."""
    parts = [str(item) for item in argv]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _run_git(args: list[str], cwd: str | Path) -> subprocess.CompletedProcess[str]:
    """Run a short Git query and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )


def collect_git_info(cwd: str | Path = ".") -> tuple[str | None, bool | None]:
    """Return ``(commit, dirty)`` for the current Git checkout if available."""
    try:
        commit = _run_git(["rev-parse", "HEAD"], cwd).stdout.strip()
        status = _run_git(["status", "--porcelain"], cwd).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None

    return (commit or None), bool(status.strip())


def collect_package_versions(names: Iterable[str]) -> dict[str, str | None]:
    """Return installed package versions without importing the packages."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def build_run_manifest(
        *,
        argv: list[str],
        input_path: str | Path,
        output_path: str | Path,
        output_dir: str | Path,
        runtime_seconds: float,
        seed: int,
        snr_db: float,
        modulation: str,
        channel: str,
        generated_files: list[str],
        cwd: str | Path = ".") -> dict:
    """Build a JSON-serialisable manifest for one successful CLI run."""
    git_commit, git_dirty = collect_git_info(cwd)
    input_target = Path(input_path)
    output_target = Path(output_path)
    manifest = {
        "schema_version": "1.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "command": _format_command([sys.executable, *argv]),
        "python_version": sys.version,
        "platform": platform.platform(),
        "package_versions": collect_package_versions(
            ("numpy", "scipy", "matplotlib")
        ),
        "input_path": str(input_target),
        "input_sha256": file_sha256(input_target),
        "output_path": str(output_target),
        "output_sha256": file_sha256(output_target),
        "runtime_seconds": float(runtime_seconds),
        "seed": int(seed),
        "snr_db": float(snr_db),
        "modulation": str(modulation),
        "channel": str(channel),
        "generated_files": [str(name) for name in generated_files],
    }
    return manifest


def write_run_manifest(manifest: dict, output_dir: str | Path) -> Path:
    """Write ``run_manifest.json`` and return its path."""
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return manifest_path
