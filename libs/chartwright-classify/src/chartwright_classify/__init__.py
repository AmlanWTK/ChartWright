"""Document classification (CP14): page image -> DocType via the CP11 model gateway."""

from __future__ import annotations

from chartwright_classify.classifier import ClassificationResult, classify_packet

__all__ = ["ClassificationResult", "classify_packet"]

__version__ = "0.1.0"
