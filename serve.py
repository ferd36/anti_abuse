#!/usr/bin/env python3
"""
Start the Flask server and browse data in the UI.

Usage:
    python serve.py [--port PORT]
"""

from __future__ import annotations

import argparse

from api.server import _DB_PATH, _STATIC_DIR, app


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the anti-abuse UI server")
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port to run the server on",
    )
    args = parser.parse_args()

    print(f"Database: {_DB_PATH}")
    print(f"Static:   {_STATIC_DIR}")
    print(f"Starting server on http://127.0.0.1:{args.port}")
    app.run(debug=True, port=args.port)


if __name__ == "__main__":
    main()
