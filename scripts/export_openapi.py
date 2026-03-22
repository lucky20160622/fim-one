#!/usr/bin/env python3
"""Export FastAPI OpenAPI spec to docs/openapi.json.

Usage::

    uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    from fim_one.web.app import create_app

    app = create_app()
    spec = app.openapi()

    out = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    print(f"Exported {len(spec.get('paths', {}))} paths to {out}")


if __name__ == "__main__":
    main()
