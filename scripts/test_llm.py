#!/usr/bin/env python3
"""
test_llm.py — Test LLM connectivity and display configuration + latency.

Usage:
    python scripts/test_llm.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from conscious_entity.runtime_env import load_project_env

console = Console()


def _redact(value: str | None, keep: int = 6) -> str:
    if not value:
        return "[dim]not set[/dim]"
    if len(value) <= keep * 2:
        return "[yellow]***[/yellow]"
    return value[:keep] + "..." + value[-keep:]


def main() -> None:
    load_project_env()

    import os
    from conscious_entity.llm.claude_client import ClaudeClient, ClaudeConfigurationError

    # --- config table ---
    cfg_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    cfg_table.add_column("Key", style="cyan", no_wrap=True)
    cfg_table.add_column("Value")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    model_env = os.environ.get("ENTITY_LLM_MODEL")
    endpoint = os.environ.get("ENTITY_LLM_MESSAGES_ENDPOINT")
    disable_proxy = os.environ.get("ENTITY_LLM_DISABLE_SYSTEM_PROXY")

    if endpoint:
        mode = "custom endpoint"
    elif auth_token:
        mode = "supplier (auth_token)"
    elif api_key:
        mode = "official (api_key)"
    else:
        mode = "[red]none configured[/red]"

    cfg_table.add_row("Mode", f"[bold]{mode}[/bold]")
    cfg_table.add_row("ANTHROPIC_API_KEY", _redact(api_key))
    cfg_table.add_row("ANTHROPIC_AUTH_TOKEN", _redact(auth_token))
    cfg_table.add_row("ANTHROPIC_BASE_URL", base_url or "[dim]not set[/dim]")
    cfg_table.add_row("ENTITY_LLM_MODEL", model_env or "[dim]not set (default)[/dim]")
    cfg_table.add_row("ENTITY_LLM_MESSAGES_ENDPOINT", endpoint or "[dim]not set[/dim]")
    cfg_table.add_row("ENTITY_LLM_DISABLE_SYSTEM_PROXY", disable_proxy or "[dim]not set[/dim]")

    console.print(Panel(cfg_table, title="[bold]LLM Configuration[/bold]", border_style="blue"))

    # --- connectivity test ---
    try:
        client = ClaudeClient()
    except ClaudeConfigurationError as exc:
        console.print(f"[red bold]Configuration error:[/red bold] {exc}")
        sys.exit(1)

    console.print("\n[bold]Testing LLM connectivity...[/bold]")

    prompt = "Reply with exactly: OK"
    start = time.monotonic()
    try:
        result = client.complete(
            system="You are a test agent. Follow instructions exactly.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
    except Exception as exc:
        console.print(f"[red]Exception during call:[/red] {exc}")
        sys.exit(1)

    result_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    result_table.add_column("Key", style="cyan", no_wrap=True)
    result_table.add_column("Value")

    if result:
        result_table.add_row("Status", "[green bold]✓ SUCCESS[/green bold]")
        result_table.add_row("Latency", f"{duration_ms} ms")
        result_table.add_row("Model", client._model)
        result_table.add_row("Response", f'[italic]"{result.strip()}"[/italic]')
    else:
        result_table.add_row("Status", "[red bold]✗ FAILED[/red bold] (empty response)")
        result_table.add_row("Latency", f"{duration_ms} ms")
        result_table.add_row("Model", client._model)

    color = "green" if result else "red"
    console.print(Panel(result_table, title="[bold]Test Result[/bold]", border_style=color))

    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
