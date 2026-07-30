"""Smoke-check the local development platform (CP04-L).

Dependency-free by design: uses plain TCP connects (plus a minimal HTTP request where a
service speaks HTTP) so it runs in any environment without extra packages. Deeper,
protocol-level checks arrive with the services that use each system (CP08+).

Usage:  uv run python scripts/check_local_stack.py
Exit code 0 = all services healthy; 1 = at least one failed.
"""

from __future__ import annotations

import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

TIMEOUT_S = 5.0


@dataclass(frozen=True)
class TcpCheck:
    name: str
    host: str
    port: int


@dataclass(frozen=True)
class HttpCheck:
    name: str
    url: str
    ok_statuses: tuple[int, ...] = (200,)


TCP_CHECKS: list[TcpCheck] = [
    TcpCheck("postgres", "localhost", 5432),
    TcpCheck("redis", "localhost", 6379),
    TcpCheck("kafka", "localhost", 9092),
    TcpCheck("temporal", "localhost", 7233),
]

HTTP_CHECKS: list[HttpCheck] = [
    # MinIO liveness endpoint; 200 when the S3 API is up.
    HttpCheck("minio", "http://localhost:9000/minio/health/live"),
    # Temporal UI serves its SPA at root.
    HttpCheck("temporal-ui", "http://localhost:8233/", ok_statuses=(200, 301, 302)),
]


def check_tcp(c: TcpCheck) -> tuple[bool, str]:
    try:
        with socket.create_connection((c.host, c.port), timeout=TIMEOUT_S):
            return True, f"tcp {c.host}:{c.port} accepts connections"
    except OSError as exc:
        return False, f"tcp {c.host}:{c.port} — {exc}"


def check_http(c: HttpCheck) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(c.url, method="GET")  # noqa: S310 - fixed localhost URLs
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            ok = resp.status in c.ok_statuses
            return ok, f"http {c.url} -> {resp.status}"
    except urllib.error.HTTPError as exc:
        ok = exc.code in c.ok_statuses
        return ok, f"http {c.url} -> {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"http {c.url} — {exc}"


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    for tcp in TCP_CHECKS:
        ok, detail = check_tcp(tcp)
        results.append((tcp.name, ok, detail))
    for http in HTTP_CHECKS:
        ok, detail = check_http(http)
        results.append((http.name, ok, detail))

    width = max(len(name) for name, _, _ in results)
    all_ok = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        all_ok &= ok
        print(f"  [{status}] {name:<{width}}  {detail}")

    print()
    if all_ok:
        print("Local stack healthy: all services reachable.")
        return 0
    print("Local stack UNHEALTHY: one or more services failed (is `make local-up` running?).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
