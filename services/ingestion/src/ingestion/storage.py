"""ObjectStorage moved to libs/chartwright-storage in CP13 (ADR-0009), so
services/pipeline can share it for the NORMALIZED stage's page storage without
depending on the ingestion service. Re-exported here so every existing import
(``from ingestion.storage import ObjectStorage``) keeps working unchanged.
"""

from __future__ import annotations

from chartwright_storage import ObjectStorage

__all__ = ["ObjectStorage"]
