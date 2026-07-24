"""FastAPI layer for the candidate-scoring system.

Thin HTTP wrappers over ``db.mongo`` and ``scorer.service`` — no business
logic lives here. Import the app directly::

    uvicorn api.main:app --reload

or run as a module::

    python -m api
"""
from .main import app, create_app

__all__ = ["app", "create_app"]
