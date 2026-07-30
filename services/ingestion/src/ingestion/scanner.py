"""Malware scanning behind a protocol seam.

The architecture requires every upload scanned before processing (FR-ING-05). Locally we
run a lightweight scanner that detects the standard EICAR test signature — enough to
prove the quarantine path end-to-end without running a full ClamAV container (heavy:
~1GB+ RAM and large definition downloads). The production deployment swaps in a real
engine (ClamAV/cloud scanning) behind the same protocol; that swap is configuration and
one adapter class, not a redesign. Recorded as a known dev/prod difference.
"""

from __future__ import annotations

from typing import Protocol


class ScanVerdict:
    CLEAN = "clean"
    INFECTED = "infected"


class Scanner(Protocol):
    def scan(self, data: bytes) -> tuple[str, str | None]:
        """Return (verdict, threat_name|None)."""
        ...


# The industry-standard antivirus test string (harmless by definition, detected by all
# real engines). Split so this source file itself never contains the contiguous signature.
_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class EicarScanner:
    """Local/dev scanner: flags the EICAR test signature; everything else is clean."""

    def scan(self, data: bytes) -> tuple[str, str | None]:
        if _EICAR in data:
            return (ScanVerdict.INFECTED, "EICAR-Test-Signature")
        return (ScanVerdict.CLEAN, None)
