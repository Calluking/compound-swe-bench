#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from patch_snapshot import save_patch_snapshot
from render_claude_stream_jsonl import render_file

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LOGS_DIR = ROOT / "output_logs"
PREPARE_TASK = ROOT / "scripts" / "prepare_task.py"
PRINT_LOCK = threading.Lock()
RUN_KIND = "same_session"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def emit(event: dict) -> None:
    with PRINT_LOCK:
        print(json.dumps(event, ensure_ascii=False), flush=True)


def write_log(log_path: Path, event: dict) -> None:
    record = json.dumps(event, ensure_ascii=False)
    with PRINT_LOCK:
        print(record, flush=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(record + "\n")


def prepare_task(task_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(PREPARE_TASK), task_id],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    emit(
        {
            "event": "task_prepared",
            "timestamp": utc_now(),
            **payload,
        }
    )
    return payload


def build_prompt(task_md_path: Path, task_number: int, task_count: int) -> str:
    task_prompt = task_md_path.read_text(encoding="utf-8").strip()
    return f"""You are running task {task_number} of {task_count} in a shared Claude session.

Treat this task as independent from earlier tasks in the conversation. Use only the repository checkout and task files named below for this task.
The Claude process cwd is the benchmark runner root so the session can be resumed across tasks; use the absolute workspace path from the task text when reading, editing, or running commands.

{task_prompt}
"""


def update_session_id(payload: dict, session: dict[str, str | None]) -> None:
    if payload.get("is_error"):
        return

    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        session["id"] = session_id
        return

    message = payload.get("message")
    if isinstance(message, dict):
        session_id = message.get("session_id")
        if isinstance(session_id, str) and session_id:
            session["id"] = session_id


def stream_reader(
    task_id: str,
    stream_name: str,
    pipe,
    log_path: Path,
    session: dict[str, str | None],
) -> None:
    for raw_line in pipe:
        line = raw_line.rstrip("\n")
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = {"raw": line}
        else:
            if stream_name == "stdout":
                update_session_id(payload, session)

        event = {
            "event": "claude_output",
            "timestamp": utc_now(),
            "task_id": task_id,
            "stream": stream_name,
            "payload": payload,
        }
        write_log(log_path, event)


def run_claude(
    task_meta: dict,
    task_number: int,
    task_count: int,
    session_id: str | None,
    model: str | None,
    effort: str | None,
    output_dir: Path,
) -> tuple[int, str | None]:
    task_id = task_meta["task_id"]
    task_md_path = Path(task_meta["task_md"])
    task_dir = task_md_path.parent
    workspace = Path(task_meta["workspace"])
    log_path = output_dir / f"{task_id}.jsonl"
    progress_md_path = task_dir / "progress.md"
    prompt = build_prompt(task_md_path, task_number, task_count)

    command = [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--permission-mode",
        "bypassPermissions",
        "--dangerously-skip-permissions",
        "--add-dir",
        str(workspace),
        "--add-dir",
        str(task_dir),
    ]
    if session_id:
        command.extend(["--resume", session_id])
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["--effort", effort])

    start_event = {
        "event": "claude_started",
        "timestamp": utc_now(),
        "task_id": task_id,
        "task_number": task_number,
        "task_count": task_count,
        "workspace": str(workspace),
        "task_md": str(task_md_path),
        "progress_md": str(progress_md_path),
        "log_path": str(log_path),
        "cwd": str(ROOT),
        "resume_session_id": session_id,
        "command": command,
    }
    write_log(log_path, start_event)

    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    process.stdin.write(prompt)
    if not prompt.endswith("\n"):
        process.stdin.write("\n")
    process.stdin.close()

    session: dict[str, str | None] = {"id": session_id}
    stdout_thread = threading.Thread(
        target=stream_reader,
        args=(task_id, "stdout", process.stdout, log_path, session),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stream_reader,
        args=(task_id, "stderr", process.stderr, log_path, session),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    finish_event = {
        "event": "claude_finished",
        "timestamp": utc_now(),
        "task_id": task_id,
        "return_code": return_code,
        "session_id": session["id"],
        "progress_md": str(progress_md_path),
        "log_path": str(log_path),
    }
    write_log(log_path, finish_event)
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
    return return_code, session["id"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare 5 SWE-bench tasks and run Claude sequentially in one resumed session."
    )
    parser.add_argument(
        "task_ids",
        nargs=5,
        help="Exactly 5 SWE-bench task IDs, e.g. django__django-10914",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional Claude model alias or full model name.",
    )
    parser.add_argument(
        "--effort",
        default=None,
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Optional Claude effort level.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = OUTPUT_LOGS_DIR / RUN_KIND / run_id()
    output_dir.mkdir(parents=True, exist_ok=True)

    emit(
        {
            "event": "run_started",
            "timestamp": utc_now(),
            "task_ids": args.task_ids,
            "output_logs_dir": str(output_dir),
            "run_kind": RUN_KIND,
            "model": args.model,
            "effort": args.effort,
            "session_mode": "shared_resume",
        }
    )

    prepared_tasks: list[dict] = []
    results: dict[str, int] = {}

    for task_id in args.task_ids:
        try:
            prepared_tasks.append(prepare_task(task_id))
        except subprocess.CalledProcessError as exc:
            results[task_id] = exc.returncode or 1
            emit(
                {
                    "event": "task_failed",
                    "timestamp": utc_now(),
                    "task_id": task_id,
                    "return_code": exc.returncode,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                }
            )
        except Exception as exc:  # pragma: no cover
            results[task_id] = 1
            emit(
                {
                    "event": "task_failed",
                    "timestamp": utc_now(),
                    "task_id": task_id,
                    "error": str(exc),
                }
            )

    session_id: str | None = None
    task_count = len(prepared_tasks)
    for index, task_meta in enumerate(prepared_tasks, start=1):
        task_id = task_meta["task_id"]
        try:
            return_code, session_id = run_claude(
                task_meta,
                task_number=index,
                task_count=task_count,
                session_id=session_id,
                model=args.model,
                effort=args.effort,
                output_dir=output_dir,
            )
            results[task_id] = return_code
        except Exception as exc:  # pragma: no cover
            results[task_id] = 1
            emit(
                {
                    "event": "task_failed",
                    "timestamp": utc_now(),
                    "task_id": task_id,
                    "session_id": session_id,
                    "error": str(exc),
                }
            )

    exit_code = 0 if all(code == 0 for code in results.values()) else 1
    emit(
        {
            "event": "run_finished",
            "timestamp": utc_now(),
            "results": results,
            "session_id": session_id,
            "output_logs_dir": str(output_dir),
            "exit_code": exit_code,
        }
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
