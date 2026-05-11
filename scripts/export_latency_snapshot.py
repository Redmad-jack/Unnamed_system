#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def fetch_json(base_url: str, path: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    with urlopen(url, timeout=5) as response:  # nosec B310 - local developer API snapshot tool.
        return json.loads(response.read().decode("utf-8"))


def fmt_ms(value: Any) -> str:
    try:
        return f"{float(value):.2f} ms"
    except (TypeError, ValueError):
        return "0.00 ms"


def render_markdown(snapshot: dict[str, Any]) -> str:
    latency = snapshot.get("latency") or {}
    audio = snapshot.get("audio_latency") or {}
    llm = snapshot.get("llm_stats") or {}
    turn_summary = latency.get("summary") or {}
    audio_summary = audio.get("summary") or {}
    llm_summary = llm.get("summary") or {}
    latest_turns = latency.get("recent") or []

    lines = [
        "# Latency Snapshot",
        "",
        f"- Captured at: `{snapshot.get('captured_at')}`",
        f"- Base URL: `{snapshot.get('base_url')}`",
        "",
        "## Turn Summary",
        "",
        f"- Turns: `{turn_summary.get('total_turns', 0)}`",
        f"- Avg total: `{fmt_ms(turn_summary.get('avg_total_ms'))}`",
        f"- P95 total: `{fmt_ms(turn_summary.get('p95_total_ms'))}`",
        "",
        "| Step | Count | Avg | P95 |",
        "|---|---:|---:|---:|",
    ]

    steps = turn_summary.get("steps") or {}
    if steps:
        for name, item in sorted(
            steps.items(),
            key=lambda pair: float((pair[1] or {}).get("avg_ms") or 0),
            reverse=True,
        ):
            lines.append(
                f"| `{name}` | {item.get('count', 0)} | "
                f"{fmt_ms(item.get('avg_ms'))} | {fmt_ms(item.get('p95_ms'))} |"
            )
    else:
        lines.append("| _none_ | 0 | 0.00 ms | 0.00 ms |")

    lines.extend([
        "",
        "## Audio Summary",
        "",
        f"- Records: `{audio_summary.get('total_records', 0)}`",
        "",
        "| Kind | Count | Success | Failure | Avg | P95 |",
        "|---|---:|---:|---:|---:|---:|",
    ])

    kinds = audio_summary.get("kinds") or {}
    if kinds:
        for kind, item in sorted(
            kinds.items(),
            key=lambda pair: float((pair[1] or {}).get("avg_ms") or 0),
            reverse=True,
        ):
            lines.append(
                f"| `{kind}` | {item.get('count', 0)} | {item.get('success_count', 0)} | "
                f"{item.get('failure_count', 0)} | {fmt_ms(item.get('avg_ms'))} | "
                f"{fmt_ms(item.get('p95_ms'))} |"
            )
    else:
        lines.append("| _none_ | 0 | 0 | 0 | 0.00 ms | 0.00 ms |")

    lines.extend([
        "",
        "## LLM Summary",
        "",
        f"- Calls: `{llm_summary.get('total_calls', 0)}`",
        f"- Avg duration: `{fmt_ms(llm_summary.get('avg_duration_ms'))}`",
        f"- Success: `{llm_summary.get('success_count', 0)}`",
        f"- Failure: `{llm_summary.get('failure_count', 0)}`",
        "",
        "## Latest Turn",
        "",
    ])

    latest = latest_turns[-1] if latest_turns else None
    if latest:
        lines.extend([
            f"- Source: `{latest.get('source')}`",
            f"- Total: `{fmt_ms(latest.get('total_ms'))}`",
            f"- Success: `{latest.get('success')}`",
            "",
            "| Step | Duration | Blocking |",
            "|---|---:|---|",
        ])
        for step in latest.get("steps") or []:
            lines.append(
                f"| `{step.get('name')}` | {fmt_ms(step.get('duration_ms'))} | "
                f"{step.get('blocking')} |"
            )
    else:
        lines.append("_No recent turn records._")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export current API latency stats to JSON and Markdown.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out-dir", default="data/latency_logs")
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()

    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        snapshot = {
            "captured_at": captured_at,
            "base_url": args.base_url,
            "health": fetch_json(args.base_url, "/health"),
            "latency": fetch_json(args.base_url, f"/api/v1/stats/latency?n={args.n}"),
            "audio_latency": fetch_json(args.base_url, f"/api/v1/stats/audio-latency?n={args.n}"),
            "llm_stats": fetch_json(args.base_url, f"/api/v1/stats/llm?n={args.n}"),
        }
    except (OSError, URLError, TimeoutError) as exc:
        print(f"latency snapshot failed: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"latency-{stamp}.json"
    md_path = out_dir / f"latency-{stamp}.md"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(snapshot), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
