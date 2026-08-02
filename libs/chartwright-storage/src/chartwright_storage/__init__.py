"""chartwright-storage: S3-compatible object storage, shared across services (CP13/ADR-0009)."""

from chartwright_storage.object_storage import ObjectStorage, S3SettingsLike

__all__ = ["ObjectStorage", "S3SettingsLike"]

__version__ = "0.1.0"
