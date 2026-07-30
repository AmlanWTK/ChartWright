"""Unit tests: magic-byte detection, size limits, scanner, event contract."""

import pytest
from ingestion.events import document_received_event
from ingestion.scanner import EicarScanner, ScanVerdict
from ingestion.validation import (
    FileType,
    ValidationError,
    detect_file_type,
    extension_for,
    validate_size,
)


class TestFileTypeDetection:
    @pytest.mark.parametrize(
        ("prefix", "expected"),
        [
            (b"%PDF-1.7 rest", FileType.PDF),
            (b"\x89PNG\r\n\x1a\n....", FileType.PNG),
            (b"\xff\xd8\xff\xe0....", FileType.JPEG),
            (b"II*\x00....", FileType.TIFF),
            (b"MM\x00*....", FileType.TIFF),
        ],
    )
    def test_supported_types(self, prefix: bytes, expected: FileType) -> None:
        assert detect_file_type(prefix) == expected

    def test_client_declared_type_is_ignored(self) -> None:
        """An .exe renamed to .pdf is still rejected: bytes decide, not names."""
        with pytest.raises(ValidationError) as exc:
            detect_file_type(b"MZ\x90\x00 windows executable bytes")
        assert exc.value.code == "UNSUPPORTED_TYPE"

    def test_extension_mapping_total(self) -> None:
        for ftype in FileType:
            assert extension_for(ftype).startswith(".")


class TestSizeValidation:
    def test_empty_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_size(b"", max_bytes=100)
        assert exc.value.code == "EMPTY_FILE"

    def test_oversize_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_size(b"x" * 101, max_bytes=100)
        assert exc.value.code == "TOO_LARGE"

    def test_at_limit_accepted(self) -> None:
        validate_size(b"x" * 100, max_bytes=100)  # no raise


class TestScanner:
    def test_clean_file(self) -> None:
        verdict, threat = EicarScanner().scan(b"%PDF-1.7 harmless content")
        assert verdict == ScanVerdict.CLEAN
        assert threat is None

    def test_eicar_detected(self) -> None:
        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        verdict, threat = EicarScanner().scan(b"%PDF-1.7" + eicar)
        assert verdict == ScanVerdict.INFECTED
        assert threat == "EICAR-Test-Signature"


class TestEventContract:
    def test_received_event_has_no_phi_and_required_keys(self) -> None:
        import uuid

        event_type, payload = document_received_event(
            tenant_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            source_channel="api",
            dedupe=False,
        )
        assert event_type == "document.received"
        assert set(payload) == {
            "tenant_id",
            "document_id",
            "source_channel",
            "dedupe",
            "occurred_at",
        }  # references only — adding fields here needs a PHI review
