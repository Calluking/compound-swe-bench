#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from common import fail_to_pass_command, fetch_task, prepare_workspace, task_dir


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/test_task.py <task_id>")
    task_id = sys.argv[1]
    row = fetch_task(task_id)
    workspace = prepare_workspace(row)
    cmd = fail_to_pass_command(row)
    completed = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True)

    out = {
        "task_id": task_id,
        "repo": row["repo"],
        "workspace": str(workspace),
        "command": cmd,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    out_path = task_dir(row) / "test_result.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "task_id": task_id,
        "result": str(out_path),
        "exit_code": completed.returncode,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
