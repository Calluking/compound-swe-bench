#!/usr/bin/env python3
"""Generate scikit-learn comparison markdown and visualization."""

import json
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np


def parse_logs(log_dirs):
    """Parse logs from multiple directories."""
    all_metrics = {}

    for log_dir in log_dirs:
        log_path = Path(log_dir)
        if not log_path.exists():
            continue

        for log_file in sorted(log_path.glob("*.jsonl")):
            task_id = log_file.stem

            timestamps = []
            turn_count = 0

            with open(log_file) as f:
                for line in f:
                    data = json.loads(line)
                    ts_str = data.get("timestamp")
                    if ts_str:
                        timestamps.append(ts_str)
                    turn_count += 1

            if timestamps:
                start = datetime.fromisoformat(timestamps[0].replace('+00:00', '+00:00'))
                end = datetime.fromisoformat(timestamps[-1].replace('+00:00', '+00:00'))
                elapsed_minutes = (end - start).total_seconds() / 60

                if task_id not in all_metrics:
                    all_metrics[task_id] = {"times": [], "turns": []}
                all_metrics[task_id]["times"].append(elapsed_minutes)
                all_metrics[task_id]["turns"].append(turn_count)

    return all_metrics


def main():
    # Parse all logs
    parallel_dirs = [
        "/mnt/d/dataD/postundergraduate/compound-swe-bench/output_logs/parallel/20260430T030135Z",
        "/mnt/d/dataD/postundergraduate/compound-swe-bench/output_logs/parallel/20260430T030901Z",
        "/mnt/d/dataD/postundergraduate/compound-swe-bench/output_logs/parallel/20260430T032103Z"
    ]

    same_session_dir = "/mnt/d/dataD/postundergraduate/compound-swe-bench/output_logs/same_session/20260430T063815Z"

    parallel_raw = parse_logs(parallel_dirs)
    same_session_raw = parse_logs([same_session_dir])

    # Aggregate parallel runs (take average across the 3 parallel runs)
    parallel_metrics = {}
    for task_id, data in parallel_raw.items():
        parallel_metrics[task_id] = {
            "elapsed_minutes": np.mean(data["times"]),
            "turns": np.mean(data["turns"]),
            "times": data["times"]
        }

    # Same session has one run per task
    same_session_metrics = {}
    for task_id, data in same_session_raw.items():
        same_session_metrics[task_id] = {
            "elapsed_minutes": data["times"][0] if data["times"] else 0,
            "turns": data["turns"][0] if data["turns"] else 0,
        }

    # Calculate summary stats
    parallel_total_time = sum(m["elapsed_minutes"] for m in parallel_metrics.values())
    same_session_total_time = sum(m["elapsed_minutes"] for m in same_session_metrics.values())
    parallel_total_turns = sum(m["turns"] for m in parallel_metrics.values())
    same_session_total_turns = sum(m["turns"] for m in same_session_metrics.values())

    # Get max time for wall-clock (represents longest parallel task)
    parallel_wall_clock = max(m["elapsed_minutes"] for m in parallel_metrics.values())

    print("Summary Statistics:")
    print(f"Parallel wall-clock (lower bound): {parallel_wall_clock:.2f}m")
    print(f"Parallel total time: {parallel_total_time:.2f}m")
    print(f"Same-session total time: {same_session_total_time:.2f}m")
    print(f"Parallel total turns: {parallel_total_turns:.0f}")
    print(f"Same-session total turns: {same_session_total_turns:.0f}")
    print(f"Turn delta: {same_session_total_turns - parallel_total_turns:.0f}")

    # Create visualization
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))

    # Sort tasks by task ID
    task_ids = sorted(parallel_metrics.keys())

    # Time comparison
    times_parallel = [parallel_metrics[t]["elapsed_minutes"] for t in task_ids]
    times_same = [same_session_metrics[t]["elapsed_minutes"] for t in task_ids]

    x = np.arange(len(task_ids))
    width = 0.35

    ax = axes[0]
    bars1 = ax.bar(x - width/2, times_parallel, width, label='Parallel (avg of 3 runs)', color='#1f77b4', alpha=0.8)
    bars2 = ax.bar(x + width/2, times_same, width, label='Same Session', color='#ff7f0e', alpha=0.8)

    ax.set_ylabel('Time (minutes)', fontsize=11, fontweight='bold')
    ax.set_title('Task Execution Time Comparison: Parallel vs Same Session', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(task_ids, rotation=45, ha='right', fontsize=9)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}m',
                    ha='center', va='bottom', fontsize=8)

    # Turns comparison
    turns_parallel = [parallel_metrics[t]["turns"] for t in task_ids]
    turns_same = [same_session_metrics[t]["turns"] for t in task_ids]

    ax = axes[1]
    bars1 = ax.bar(x - width/2, turns_parallel, width, label='Parallel (avg of 3 runs)', color='#1f77b4', alpha=0.8)
    bars2 = ax.bar(x + width/2, turns_same, width, label='Same Session', color='#ff7f0e', alpha=0.8)

    ax.set_xlabel('Task ID', fontsize=11, fontweight='bold')
    ax.set_ylabel('Number of Turns', fontsize=11, fontweight='bold')
    ax.set_title('Turn Count Comparison: Parallel vs Same Session', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(task_ids, rotation=45, ha='right', fontsize=9)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    plt.savefig('/mnt/d/dataD/postundergraduate/compound-swe-bench/scikit-run-comparison.png', dpi=150, bbox_inches='tight')
    print("\nChart saved to scikit-run-comparison.png")

    # Generate markdown content
    task_ids_sorted = sorted(parallel_metrics.keys())

    markdown_content = f"""# Scikit-Learn Task Run Comparison

![Scikit-learn task run comparison charts](scikit-run-comparison.png)

Comparison of parallel runs (`output_logs/parallel/20260430T030135Z`, `20260430T030901Z`, `20260430T032103Z`) and same-session run (`output_logs/same_session/20260430T063815Z`).

Task order: {', '.join('`' + t.replace('scikit-learn__scikit-learn-', '') + '`' for t in task_ids_sorted[:5])}.

## Summary

| Metric | Value |
| --- | ---: |
| Parallel wall-clock lower bound | {parallel_wall_clock:.2f}m |
| Parallel summed task time | {parallel_total_time:.2f}m |
| Same-session summed task time | {same_session_total_time:.2f}m |
| Parallel total turns | {int(parallel_total_turns)} |
| Same-session total turns | {int(same_session_total_turns)} |
| Turn delta, same minus parallel | {int(same_session_total_turns - parallel_total_turns)} |

## Time By Task

| Task | Parallel | Same Session |
| --- | ---: | ---: |
"""

    for task_id in task_ids_sorted:
        task_short = task_id.replace('scikit-learn__scikit-learn-', '')
        parallel_time = parallel_metrics[task_id]["elapsed_minutes"]
        same_time = same_session_metrics[task_id]["elapsed_minutes"]
        markdown_content += f"| `{task_short}` | {parallel_time:.2f}m | {same_time:.2f}m |\n"

    markdown_content += """
## Total Turns By Task

| Task | Parallel | Same Session |
| --- | ---: | ---: |
"""

    for task_id in task_ids_sorted:
        task_short = task_id.replace('scikit-learn__scikit-learn-', '')
        parallel_turns = int(parallel_metrics[task_id]["turns"])
        same_turns = int(same_session_metrics[task_id]["turns"])
        markdown_content += f"| `{task_short}` | {parallel_turns} | {same_turns} |\n"

    # Write markdown file
    md_path = Path("/mnt/d/dataD/postundergraduate/compound-swe-bench/scikit-run-comparison.md")
    md_path.write_text(markdown_content)
    print(f"Markdown file created: scikit-run-comparison.md")


if __name__ == "__main__":
    main()
