#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from og_memory_runtime import OGMemoryRuntime
from patch_snapshot import save_patch_snapshot
from render_claude_stream_jsonl import render_file

ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LOGS_DIR = BENCH_ROOT / "output_logs"
PREPARE_TASK = BENCH_ROOT / "scripts" / "prepare_task.py"
PRINT_LOCK = threading.Lock()
RUN_KIND = "parallel_og"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def emit(event: dict) -> None:
    with PRINT_LOCK:
        print(json.dumps(event, ensure_ascii=False), flush=True)


def prepare_task(task_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(PREPARE_TASK), task_id],
        cwd=str(BENCH_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    emit({"event": "task_prepared", "timestamp": utc_now(), **payload})
    return payload


def build_prompt(task_md_path: Path) -> str:
    task_prompt = task_md_path.read_text(encoding="utf-8").strip()
    return (
        task_prompt
        + "\n\nFinal answer must include:\n"
        + "- root cause\n"
        + "- changed files\n"
        + "- verification command/output\n\n"
        + "## MCP requirement\n"
        + "Before you edit any source/code file, call the og-memory MCP tool search_code at least once.\n"
        + "Use path=$WORK_DIR and query terms using how you would call 'grep' tool.\n"
        + "Compare multiple top L2 chunk hits, then patch only the best-matching files.\n"
        + "Do not use Claude's built-in `Edit` tool for this task.\n"
        + "Treat `mcp__og-memory__edit_file` as your edit tool.\n\n"
        + "## MCP efficiency policy (turn/token reduction)\n"
        + "- Treat og-memory `search_code` as a replacement for broad `grep` and exploratory `read`.\n"
        + "- Minimize extra search loops: prefer 1-2 high-quality `search_code` calls with focused symbol-level queries.\n"
        + "- If returned snippets already include the target file and useful line context, act directly:\n"
        + "  - edit the code immediately with `mcp__og-memory__edit_file`, or\n"
        + "  - run the next concrete action (patch/test) without additional broad reads.\n"
        + "- Avoid reading many unrelated files after a good hit; keep turns and token usage low.\n"
        + "- Only perform extra reads when required to verify safety or dependencies for the exact patch.\n"
        + "- Once the code is retrieved via `search_code`, skip the built-in 'Read'/'Edit' path and proceed directly to analyzing and editing with MCP tools.\n"
    )


def stream_reader(task_id: str, stream_name: str, pipe, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log_file:
        for raw_line in pipe:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"raw": line}
            event = {
                "event": "claude_output",
                "timestamp": utc_now(),
                "task_id": task_id,
                "stream": stream_name,
                "payload": payload,
            }
            record = json.dumps(event, ensure_ascii=False)
            with PRINT_LOCK:
                print(record, flush=True)
                log_file.write(record + "\n")
                log_file.flush()


def run_claude(task_meta: dict, model: str | None, effort: str | None, output_dir: Path, runtime: OGMemoryRuntime) -> int:
    task_id = task_meta["task_id"]
    task_md_path = Path(task_meta["task_md"])
    task_dir = task_md_path.parent
    workspace = Path(task_meta["workspace"])
    log_path = output_dir / f"{task_id}.jsonl"
    progress_md_path = task_dir / "progress.md"
    prompt = build_prompt(task_md_path)

    command = [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--permission-mode",
        "bypassPermissions",
        "--dangerously-skip-permissions",
        "--strict-mcp-config",
        "--mcp-config",
        str(runtime.mcp_json),
        "--add-dir",
        str(task_dir),
        "--add-dir",
        str(workspace),
    ]
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["--effort", effort])

    emit(
        {
            "event": "claude_started",
            "timestamp": utc_now(),
            "task_id": task_id,
            "workspace": str(workspace),
            "task_md": str(task_md_path),
            "progress_md": str(progress_md_path),
            "log_path": str(log_path),
            "mcp_config": str(runtime.mcp_json),
            "command": command,
        }
    )

    env = runtime.env.copy()
    env["CLAUDE_CODE_DEBUG_LOGS_DIR"] = str(output_dir)
    env["PYTHONPATH"] = f"{workspace}{os.pathsep}{env.get('PYTHONPATH','')}"

    process = subprocess.Popen(
        command,
        cwd=str(workspace),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    assert process.stdin and process.stdout and process.stderr
    process.stdin.write(prompt)
    if not prompt.endswith("\n"):
        process.stdin.write("\n")
    process.stdin.close()

    stdout_thread = threading.Thread(target=stream_reader, args=(task_id, "stdout", process.stdout, log_path), daemon=True)
    stderr_thread = threading.Thread(target=stream_reader, args=(task_id, "stderr", process.stderr, log_path), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    emit(
        {
            "event": "claude_finished",
            "timestamp": utc_now(),
            "task_id": task_id,
            "return_code": return_code,
            "progress_md": str(progress_md_path),
            "log_path": str(log_path),
        }
    )
    render_file(log_path)
    patch_path = save_patch_snapshot(task_id, workspace, output_dir)
    emit(
        {
            "event": "task_patch_saved",
            "timestamp": utc_now(),
            "task_id": task_id,
            "patch_path": str(patch_path),
        }
    )
    return return_code


def worker(task_meta: dict, model: str | None, effort: str | None, output_dir: Path, runtime: OGMemoryRuntime, results: dict[str, int]) -> None:
    task_id = task_meta["task_id"]
    try:
        results[task_id] = run_claude(task_meta, model, effort, output_dir, runtime)
    except Exception as exc:
        results[task_id] = 1
        emit({"event": "task_failed", "timestamp": utc_now(), "task_id": task_id, "error": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare SWE-bench tasks and run Claude with oG-memory MCP in parallel.")
    parser.add_argument("task_ids", nargs="+", help="One or more SWE-bench task IDs")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001", help="Claude model name")
    parser.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"], help="Optional Claude effort level.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = OUTPUT_LOGS_DIR / RUN_KIND / run_id()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = OGMemoryRuntime(ROOT, output_dir)
    runtime.start()
    emit(
        {
            "event": "run_started",
            "timestamp": utc_now(),
            "task_ids": args.task_ids,
            "output_logs_dir": str(output_dir),
            "run_kind": RUN_KIND,
            "model": args.model,
            "effort": args.effort,
            "mcp_config": str(runtime.mcp_json),
        }
    )

    prepared_tasks: list[dict] = []
    results: dict[str, int] = {}
    try:
        for task_id in args.task_ids:
            try:
                prepared_tasks.append(prepare_task(task_id))
            except subprocess.CalledProcessError as exc:
                results[task_id] = exc.returncode or 1
                emit({"event": "task_failed", "timestamp": utc_now(), "task_id": task_id, "return_code": exc.returncode, "stdout": exc.stdout, "stderr": exc.stderr})
            except Exception as exc:
                results[task_id] = 1
                emit({"event": "task_failed", "timestamp": utc_now(), "task_id": task_id, "error": str(exc)})

        threads = [
            threading.Thread(target=worker, args=(task_meta, args.model, args.effort, output_dir, runtime, results), daemon=True)
            for task_meta in prepared_tasks
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        runtime.stop()

    exit_code = 0 if all(code == 0 for code in results.values()) else 1
    emit({"event": "run_finished", "timestamp": utc_now(), "run_kind": RUN_KIND, "output_logs_dir": str(output_dir), "results": results, "exit_code": exit_code})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
