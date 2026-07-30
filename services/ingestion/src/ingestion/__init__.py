"""Ingestion service (CP09): the front door of the document pipeline."""

from ingestion.intake import IntakeResult, IntakeService

__all__ = ["IntakeResult", "IntakeService"]
__version__ = "0.1.0"
