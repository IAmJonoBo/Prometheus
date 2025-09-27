"""Ingestion stage package.

Exports base interfaces so connectors and normalisers can register with the
pipeline orchestrator.
"""

from .service import IngestionService

__all__ = ["IngestionService"]
