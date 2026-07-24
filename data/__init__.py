"""Synthetic data package — vacancy/resume generator with ground-truth labels."""
from .synthetic import generate_dataset, generate_resume, generate_vacancy

__all__ = ["generate_dataset", "generate_resume", "generate_vacancy"]
