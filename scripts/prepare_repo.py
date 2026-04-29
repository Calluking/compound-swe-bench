#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

from common import prepare_workspace, write_task_md

DATASET = "princeton-nlp/SWE-bench_Lite"
SPLIT = "test"
BASE_URL = "https://datasets-server.huggingface.co/rows"


def fetch_repo_tasks(target_repo: str) -> list[dict]:
    def fetch(offset: int, length: int) -> dict:
        q = urllib.parse.urlencode(
            {
                "dataset": DATASET,
                "config": "default",
                "split": SPLIT,
                "offset": str(offset),
                "length": str(length),
            }
        )
        with urllib.request.urlopen(f"{BASE_URL}?{q}", timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))

    first = fetch(0, 1)
    total = int(first.get("num_rows_total", 0))
    rows: list[dict] = []
    for offset in range(0, total, 100):
        payload = fetch(offset, min(100, total - offset))
        for item in payload.get("rows", []):
            row = item["row"]
            if row["repo"] == target_repo:
                rows.append(row)
    rows.sort(key=lambda row: row["instance_id"])
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/prepare_repo.py <repo>  # e.g. django/django")

    target_repo = sys.argv[1]
    rows = fetch_repo_tasks(target_repo)
    if not rows:
        raise SystemExit(f"No SWE-bench Lite test tasks found for repo: {target_repo}")

    prepared = []
    for row in rows:
        workspace = prepare_workspace(row)
        task_md = write_task_md(row, workspace)
        prepared.append(
            {
                "task_id": row["instance_id"],
                "workspace": str(workspace),
                "task_md": str(task_md),
            }
        )

    print(
        json.dumps(
            {
                "repo": target_repo,
                "task_count": len(prepared),
                "tasks": prepared,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

