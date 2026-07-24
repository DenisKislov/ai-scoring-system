"""Entry point: ``python -m api`` — run the FastAPI service with uvicorn.

Host/port/reload are configurable via env (``API_HOST``, ``API_PORT``,
``API_RELOAD``); defaults are 127.0.0.1:8000, reload off.
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "api.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=bool(os.environ.get("API_RELOAD", "")),
    )


if __name__ == "__main__":
    main()
