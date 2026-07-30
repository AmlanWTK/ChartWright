"""Deterministic upload validation: magic-byte file-type detection + size limits.

We never trust the client's declared content-type or filename extension — the file's
leading bytes decide. Unknown/unsupported types are rejected before any processing.
"""

from __future__ import annotations

from enum import StrEnum


class FileType(StrEnum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"


_MAGIC: list[tuple[bytes, FileType]] = [
    (b"%PDF", FileType.PDF),
    (b"\x89PNG\r\n\x1a\n", FileType.PNG),
    (b"\xff\xd8\xff", FileType.JPEG),
    (b"II*\x00", FileType.TIFF),  # little-endian TIFF (incl. multi-page fax)
    (b"MM\x00*", FileType.TIFF),  # big-endian TIFF
]

_EXTENSION: dict[FileType, str] = {
    FileType.PDF: ".pdf",
    FileType.PNG: ".png",
    FileType.JPEG: ".jpg",
    FileType.TIFF: ".tiff",
}


class ValidationError(Exception):
    """Upload rejected for a deterministic, client-fixable reason."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def detect_file_type(data: bytes) -> FileType:
    """Identify the file type from magic bytes; raise if unsupported."""
    for magic, ftype in _MAGIC:
        if data.startswith(magic):
            return ftype
    raise ValidationError(
        code="UNSUPPORTED_TYPE",
        detail="File type not supported. Accepted: PDF, PNG, JPEG, TIFF.",
    )


def validate_size(data: bytes, max_bytes: int) -> None:
    if len(data) == 0:
        raise ValidationError(code="EMPTY_FILE", detail="Uploaded file is empty.")
    if len(data) > max_bytes:
        raise ValidationError(
            code="TOO_LARGE",
            detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.",
        )


def extension_for(ftype: FileType) -> str:
    return _EXTENSION[ftype]
