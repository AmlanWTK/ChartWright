"""Diagnostic: why is object storage unreachable? Run when S3 calls fail locally.

Four causes fit an ``InvalidAccessKeyId`` when compose and config agree on the creds.
This separates them in one run instead of one guess at a time:

  A. Environment override — a CHARTWRIGHT_* or AWS_* var beating the dev defaults.
  B. Wrong server on the port — something other than OUR MinIO answering it.
  C. MinIO up, credentials genuinely rejected — stale volume / changed root user.
  D. Nothing listening — the container is not running.

Run:  uv run python scripts/diag_minio.py
"""

from __future__ import annotations

import os

import httpx
from botocore.exceptions import ClientError, EndpointConnectionError
from ingestion.config import get_settings
from ingestion.storage import ObjectStorage


def _mask(value: str) -> str:
    """Enough to compare against compose, not enough to leak."""
    return f"{value[:3]}…({len(value)} chars)" if value else "<empty>"


def _report_environment() -> bool:
    """A. Anything in the environment that outranks the dev defaults."""
    print("=" * 70)
    print("A. ENVIRONMENT OVERRIDES")
    print("=" * 70)
    interesting = {
        k: v
        for k, v in os.environ.items()
        if k.startswith(("CHARTWRIGHT_S3", "AWS_")) or k in {"CHARTWRIGHT_S3_ENDPOINT"}
    }
    if not interesting:
        print("  none — settings come from the dev defaults in ingestion/config.py")
        return False
    for key in sorted(interesting):
        shown = (
            interesting[key]
            if "KEY" not in key and "SECRET" not in key
            else _mask(interesting[key])
        )
        print(f"  {key} = {shown}")
    print("  ^ these OVERRIDE the defaults. If any point away from local MinIO, that's the bug.")
    return True


def _report_resolved() -> tuple[str, str]:
    print()
    print("=" * 70)
    print("B. RESOLVED SETTINGS (what boto3 will actually use)")
    print("=" * 70)
    s = get_settings()
    print(f"  endpoint   : {s.s3_endpoint}")
    print(f"  access key : {s.s3_access_key!r}          (compose: 'chartwright')")
    print(f"  secret key : {_mask(s.s3_secret_key)}   (compose: 15 chars)")
    print(f"  bucket     : {s.s3_bucket}")
    print(f"  region     : {s.s3_region}")
    return s.s3_endpoint, s.s3_access_key


def _report_who_answers(endpoint: str) -> None:
    """C/D. Is that port MinIO at all? MinIO identifies itself in the Server header."""
    print()
    print("=" * 70)
    print("C. WHO IS ANSWERING THAT PORT")
    print("=" * 70)
    try:
        resp = httpx.get(endpoint, timeout=5.0)
    except httpx.ConnectError as exc:
        print(f"  NOTHING LISTENING on {endpoint}")
        print(f"  -> {exc}")
        print("  => cause D. MinIO is not running. `docker compose ps` to confirm.")
        return
    except httpx.HTTPError as exc:
        print(f"  request failed: {type(exc).__name__}: {exc}")
        return

    server = resp.headers.get("server", "<no Server header>")
    print(f"  HTTP {resp.status_code}")
    print(f"  Server: {server}")
    print(f"  body[:200]: {resp.text[:200]!r}")
    if "minio" in server.lower():
        print("  => A MinIO answers here — but NOT necessarily ours. An unauthenticated")
        print("     GET returns 403 from every MinIO alive, so this probe identifies the")
        print("     software and never the instance. `docker compose ps` settles that.")
        print("     (This line once claimed otherwise and sent an investigation down")
        print("     cause C while a different project's MinIO held the port.)")
    else:
        print("  => NOT MinIO. Something else owns that port and is rejecting the key.")


def _report_auth() -> None:
    """The real call, with the error surfaced in full rather than as a bare string."""
    print()
    print("=" * 70)
    print("D. AUTHENTICATED CALL (list_buckets — auth only, no bucket needed)")
    print("=" * 70)
    storage = ObjectStorage(get_settings())
    client = storage._client
    try:
        buckets = client.list_buckets()
    except EndpointConnectionError as exc:
        print(f"  cannot reach the endpoint at all: {exc}")
        return
    except ClientError as exc:
        err = exc.response.get("Error", {})
        meta = exc.response.get("ResponseMetadata", {})
        print(f"  Code       : {err.get('Code')}")
        print(f"  Message    : {err.get('Message')}")
        print(f"  HTTP status: {meta.get('HTTPStatusCode')}")
        print(f"  Server hdr : {meta.get('HTTPHeaders', {}).get('server', '<none>')}")
        print(f"  Request ID : {meta.get('RequestId')}")
        return
    names = [b["Name"] for b in buckets.get("Buckets", [])]
    print(f"  AUTH OK. Buckets visible: {names}")
    want = get_settings().s3_bucket
    if want in names:
        print(f"  '{want}' exists — storage is healthy; the failure is elsewhere.")
    else:
        print(f"  '{want}' MISSING — minio-init never ran. That is a different bug.")


def main() -> None:
    _report_environment()
    endpoint, _ = _report_resolved()
    _report_who_answers(endpoint)
    _report_auth()
    print()
    print("Done. Paste the whole output back.")


if __name__ == "__main__":
    main()
