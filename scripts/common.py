#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT / "repo"
DATASET = "princeton-nlp/SWE-bench_Lite"
SPLIT = "test"
BASE_URL = "https://datasets-server.huggingface.co/rows"


def fetch_task(task_id: str) -> dict:
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
        delays = [1, 2, 4, 8, 16]
        for attempt, delay in enumerate(delays, start=1):
            try:
                with urllib.request.urlopen(f"{BASE_URL}?{q}", timeout=180) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == len(delays):
                    raise
                time.sleep(delay)

    first = fetch(0, 1)
    total = int(first.get("num_rows_total", 0))
    for offset in range(0, total, 100):
        payload = fetch(offset, min(100, total - offset))
        for item in payload.get("rows", []):
            row = item["row"]
            if row["instance_id"] == task_id:
                return row
    raise RuntimeError(f"Task not found: {task_id}")


def repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def repo_dir(repo: str) -> Path:
    return REPO_ROOT / repo_slug(repo)


def cache_dir(repo: str) -> Path:
    return repo_dir(repo) / "cache"


def tasks_dir(repo: str) -> Path:
    return repo_dir(repo) / "tasks"


def task_dir(row: dict) -> Path:
    return tasks_dir(row["repo"]) / row["instance_id"]


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_cache(repo: str) -> Path:
    dest = cache_dir(repo)
    if (dest / ".git").is_dir():
        git("fetch", "--all", "--prune", cwd=dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", f"https://github.com/{repo}.git", str(dest)], check=True)
    return dest


def ensure_commit(cache: Path, commit: str) -> None:
    try:
        git("rev-parse", "--verify", f"{commit}^{{commit}}", cwd=cache)
    except subprocess.CalledProcessError:
        git("fetch", "--all", "--prune", cwd=cache)
        git("rev-parse", "--verify", f"{commit}^{{commit}}", cwd=cache)


def worktree_registered(cache: Path, workspace: Path) -> bool:
    listing = git("worktree", "list", "--porcelain", cwd=cache).stdout
    return f"worktree {workspace}" in listing


def prepare_workspace(row: dict) -> Path:
    repo = row["repo"]
    cache = ensure_cache(repo)
    ensure_commit(cache, row["base_commit"])

    td = task_dir(row)
    workspace = td / "workspace"
    td.mkdir(parents=True, exist_ok=True)

    git("worktree", "prune", cwd=cache)
    if workspace.exists():
        if worktree_registered(cache, workspace):
            git("worktree", "remove", "--force", str(workspace), cwd=cache)
        else:
            shutil.rmtree(workspace)

    git("worktree", "add", "--detach", str(workspace), row["base_commit"], cwd=cache)

    patch_path = td / "test.patch"
    patch_path.write_text(row.get("test_patch") or "", encoding="utf-8")
    subprocess.run(["git", "apply", str(patch_path)], cwd=str(workspace), check=True)

    (td / "task.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return workspace


def build_task_md(row: dict, workspace: Path) -> str:
    problem = (row.get("problem_statement") or "").strip()
    hints = (row.get("hints_text") or "").strip()
    text = f"""You are working on a real open-source project as in the SWE-bench Lite benchmark.

Repository: {row['repo']}
Checkout: parent commit (state before the fix) is {row['base_commit']}. The codebase is already checked out in {workspace}.
Do not look up or apply the original solution PR or patch from the web.

Official issue text (`problem_statement`):

---
{problem}
---
"""
    if hints:
        text += f"""

Optional prior discussion (`hints_text`):
---
{hints}
---
"""
    text += """

Implement a fix that resolves the issue following project conventions. Run or add tests as appropriate.
In your final answer, summarize root cause, files changed, and verification.
"""
    return text


def write_task_md(row: dict, workspace: Path) -> Path:
    path = task_dir(row) / "TASK.md"
    path.write_text(build_task_md(row, workspace), encoding="utf-8")
    return path


def django_label(node: str) -> str:
    import re
    match = re.fullmatch(r"(.+?) \((.+)\)", node)
    if not match:
        return node
    test_name, qual = match.groups()
    return f"{qual}.{test_name}"


def fail_to_pass_command(row: dict) -> list[str]:
    tests = json.loads(row.get("FAIL_TO_PASS") or "[]")
    if row["repo"] == "django/django":
        labels = [django_label(item) for item in tests]
        return ["python", "tests/runtests.py", *labels]
    return ["python", "-m", "pytest", *tests]
