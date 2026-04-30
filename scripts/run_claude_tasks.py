#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LOGS_DIR = ROOT / "output_logs"
PREPARE_TASK = ROOT / "scripts" / "prepare_task.py"
PRINT_LOCK = threading.Lock()
RUN_KIND = "parallel"


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


def build_prompt(task_md_path: Path) -> str:
    return task_md_path.read_text(encoding="utf-8").strip()


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


def run_claude(task_meta: dict, model: str | None, effort: str | None, output_dir: Path) -> int:
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
        "--add-dir",
        str(task_dir),
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
            "command": command,
        }
    )

    process = subprocess.Popen(
        command,
        cwd=str(workspace),
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

    stdout_thread = threading.Thread(
        target=stream_reader,
        args=(task_id, "stdout", process.stdout, log_path),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stream_reader,
        args=(task_id, "stderr", process.stderr, log_path),
        daemon=True,
    )
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
    return return_code


def worker(
    task_meta: dict,
    model: str | None,
    effort: str | None,
    output_dir: Path,
    results: dict[str, int],
) -> None:
    task_id = task_meta["task_id"]
    try:
        results[task_id] = run_claude(
            task_meta,
            model=model,
            effort=effort,
            output_dir=output_dir,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare SWE-bench tasks and run Claude on all of them in parallel."
    )
    parser.add_argument(
        "task_ids",
        nargs="+",
        help="One or more SWE-bench task IDs, e.g. sympy__sympy-15345",
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

    threads = [
        threading.Thread(
            target=worker,
            args=(task_meta, args.model, args.effort, output_dir, results),
            daemon=True,
        )
        for task_meta in prepared_tasks
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    exit_code = 0 if all(code == 0 for code in results.values()) else 1
    emit(
        {
            "event": "run_finished",
            "timestamp": utc_now(),
            "results": results,
            "output_logs_dir": str(output_dir),
            "exit_code": exit_code,
        }
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
