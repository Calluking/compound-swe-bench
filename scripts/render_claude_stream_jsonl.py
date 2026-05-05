#!/usr/bin/env python3
"""Render compound-swe-bench Claude stream JSONL logs into readable text."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _shorten(text: str, limit: int = 0) -> str:
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _decode_nested_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return value
        return _decode_nested_json(parsed)
    if isinstance(value, list):
        return [_decode_nested_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_nested_json(item) for key, item in value.items()}
    return value


def _maybe_pretty_json_string(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return value
    parsed = _decode_nested_json(parsed)
    if isinstance(parsed, (dict, list)):
        return _json_pretty(parsed)
    return value


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _format_search_code_result(text: str) -> str:
    normalized = _maybe_pretty_json_string(text)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return normalized

    lines: list[str] = ["result:"]
    for key in ("ok", "query", "hit_count"):
        if key in result:
            lines.append(f"  {key}: {result[key]!r}")

    hits = result.get("hits")
    if isinstance(hits, list):
        lines.append("  hits:")
        for idx, hit in enumerate(hits, start=1):
            if not isinstance(hit, dict):
                lines.append(f"    - {hit!r}")
                continue
            lines.append(f"    - hit {idx}:")
            for key in ("score", "start_line", "end_line", "symbol", "symbol_kind", "uri"):
                if key in hit:
                    lines.append(f"        {key}: {hit[key]!r}")
            for key in ("snippet", "content_excerpt", "overview", "abstract"):
                if key in hit:
                    lines.append(f"        {key}: |")
                    lines.append(_indent_block(str(hit.get(key) or ""), "          "))
            for key, value in hit.items():
                if key in {
                    "score",
                    "start_line",
                    "end_line",
                    "symbol",
                    "symbol_kind",
                    "uri",
                    "snippet",
                    "content_excerpt",
                    "overview",
                    "abstract",
                }:
                    continue
                lines.append(f"        {key}: {value!r}")

    for key, value in payload.items():
        if key == "result":
            continue
        lines.append(f"{key}: {value!r}")
    return "\n".join(lines)


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "tool_result":
                    parts.append(str(item.get("content") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def render_text(jsonl_path: Path, *, show_thinking: bool = False, max_chars: int = 0) -> str:
    tool_results: dict[str, dict[str, Any]] = {}
    payload_events: list[dict[str, Any]] = []
    meta_events: list[dict[str, Any]] = []

    with jsonl_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if obj.get("event") == "claude_output":
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    payload_events.append(payload)
                    if payload.get("type") == "user":
                        message = payload.get("message") or {}
                        content = message.get("content")
                        if isinstance(content, list):
                            for item in content:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") == "tool_result"
                                    and item.get("tool_use_id")
                                ):
                                    tool_results[str(item["tool_use_id"])] = item
            else:
                meta_events.append(obj)

    lines: list[str] = []
    if meta_events:
        lines.append("=== Run Metadata ===")
        for obj in meta_events:
            event = obj.get("event")
            if event in {"run_started", "claude_started", "claude_finished", "run_finished", "task_prepared", "task_failed"}:
                lines.append(_json_pretty(obj))
        lines.append("")

    turn_no = 0
    in_assistant_block = False

    for obj in payload_events:
        typ = obj.get("type")
        if typ == "user":
            message = obj.get("message") or {}
            content = message.get("content")

            if isinstance(content, list) and any(
                isinstance(item, dict) and item.get("type") == "tool_result" for item in content
            ):
                continue

            turn_no += 1
            in_assistant_block = False
            text = _extract_text_content(content)
            lines.append(f"=== Turn {turn_no} | User ===")
            lines.append(_shorten(text, max_chars))
            lines.append("")

        elif typ == "assistant":
            message = obj.get("message") or {}
            content = message.get("content") or []
            if not isinstance(content, list):
                continue

            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_uses: list[dict[str, Any]] = []

            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    text_parts.append(str(item.get("text") or ""))
                elif item_type == "thinking":
                    thinking_parts.append(str(item.get("thinking") or ""))
                elif item_type == "tool_use":
                    tool_uses.append(item)

            if text_parts or thinking_parts or tool_uses:
                if not in_assistant_block:
                    lines.append(f"=== Turn {turn_no} | Assistant ===")
                    in_assistant_block = True

            if show_thinking and thinking_parts:
                lines.append("[thinking]")
                lines.append(_shorten("\n\n".join(thinking_parts), max_chars))

            if text_parts:
                lines.append("[text]")
                lines.append(_shorten("\n\n".join(text_parts), max_chars))

            for tool in tool_uses:
                name = str(tool.get("name") or "")
                tool_input = tool.get("input")
                tool_use_id = str(tool.get("id") or "")
                lines.append(f"[tool_use] {name}")
                lines.append(_json_pretty(tool_input))

                result = tool_results.get(tool_use_id)
                if result is None:
                    lines.append("[tool_result]")
                    lines.append("(no recorded result found)")
                    continue

                content = result.get("content")
                is_error = bool(result.get("is_error"))
                label = "[tool_result:error]" if is_error else "[tool_result]"
                lines.append(label)
                if name == "mcp__og-memory__search_code":
                    text = _extract_text_content(content)
                    lines.append(_shorten(_format_search_code_result(text), max_chars))
                else:
                    if isinstance(content, (dict, list)):
                        lines.append(_shorten(_json_pretty(content), max_chars))
                    else:
                        lines.append(_shorten(_maybe_pretty_json_string(str(content or "")), max_chars))
            if text_parts or thinking_parts or tool_uses:
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_file(jsonl_path: Path, output_path: Path | None = None, *, show_thinking: bool = False, max_chars: int = 0) -> Path:
    if output_path is None:
        output_path = jsonl_path.with_name(f"{jsonl_path.stem}_render.txt")
    output_path.write_text(
        render_text(jsonl_path, show_thinking=show_thinking, max_chars=max_chars),
        encoding="utf-8",
    )
    return output_path


def render_run_dir(run_dir: Path, *, show_thinking: bool = False, max_chars: int = 0) -> list[Path]:
    rendered: list[Path] = []
    jsonls = sorted(p for p in run_dir.glob("*.jsonl") if p.is_file())
    for jsonl_path in jsonls:
        rendered.append(
            render_file(jsonl_path, show_thinking=show_thinking, max_chars=max_chars)
        )
    if len(rendered) == 1:
        latest = run_dir / "latest_session_render.txt"
        latest.write_text(rendered[0].read_text(encoding="utf-8"), encoding="utf-8")
        rendered.append(latest)
    return rendered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to a run dir or a single .jsonl file")
    parser.add_argument("--show-thinking", action="store_true", help="Include thinking blocks")
    parser.add_argument("--max-chars", type=int, default=0, help="Optional truncation limit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.path
    if path.is_dir():
        outputs = render_run_dir(path, show_thinking=args.show_thinking, max_chars=args.max_chars)
        for output in outputs:
            print(output)
        return 0
    if path.is_file():
        output = render_file(path, show_thinking=args.show_thinking, max_chars=args.max_chars)
        print(output)
        return 0
    raise SystemExit(f"Not found: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
