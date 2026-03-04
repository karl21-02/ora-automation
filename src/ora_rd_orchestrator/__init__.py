"""R&D orchestration package.

Public API:
    generate_report  — main pipeline entry point (from pipeline.py)
    PersonaRegistry  — persona YAML loader (from personas.py)
"""
from .pipeline import generate_report

__all__ = ["generate_report"]
