#!/usr/bin/env python3
"""
start_have_some_ai.py -- Start the Have Some "Ai" exhibition system.

Usage:
    python scripts/start_have_some_ai.py [--host HOST] [--port PORT] [--reload]

Examples:
    python scripts/start_have_some_ai.py
    python scripts/start_have_some_ai.py --port 8010 --reload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description='Start Have Some "Ai"')
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8010, help="Bind port (default: 8010)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on file changes")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Run:\n"
            "  pip install -e '.[api]'\n"
            "to install API dependencies."
        )
        sys.exit(1)

    print(f'Starting Have Some "Ai" at http://{args.host}:{args.port}')
    print(f"API docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "have_some_ai.interfaces.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
