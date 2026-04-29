#!/usr/bin/env python3

from __future__ import annotations

import json
import sys

from common import fetch_task, prepare_workspace, write_task_md


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/prepare_task.py <task_id>")
    task_id = sys.argv[1]
    row = fetch_task(task_id)
    workspace = prepare_workspace(row)
    task_md = write_task_md(row, workspace)
    print(json.dumps({
        "task_id": task_id,
        "repo": row["repo"],
        "workspace": str(workspace),
        "task_md": str(task_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

