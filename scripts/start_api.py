#!/usr/bin/env python3
"""
start_api.py — Start the Conscious Entity developer API server.

Usage:
    python scripts/start_api.py [--host HOST] [--port PORT] [--reload]

Examples:
    python scripts/start_api.py
    python scripts/start_api.py --port 9000 --reload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Conscious Entity developer API")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
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

    print(f"Starting developer API at http://{args.host}:{args.port}")
    print(f"Dashboard: http://{args.host}:{args.port}/")
    print(f"API docs:  http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "conscious_entity.interfaces.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
