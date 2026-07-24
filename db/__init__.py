"""Database access package — MongoDB layer shared by parser, scorer, and seeder."""
from .builders import resume_text, vacancy_text
from . import mongo

__all__ = ["mongo", "vacancy_text", "resume_text"]
