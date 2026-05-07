#!/usr/bin/env python3

from __future__ import annotations

import subprocess
from pathlib import Path


def save_patch_snapshot(task_id: str, workspace: Path, output_dir: Path) -> Path:
    patch_path = output_dir / f"{task_id}.patch"
    proc = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
    )
    patch_path.write_text(proc.stdout, encoding="utf-8")
    return patch_path
