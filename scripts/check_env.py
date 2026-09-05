"""Connectivity verification script for backing services (PostgreSQL, Redis, Qdrant, Ollama)."""

from pathlib import Path
import socket
import sys
import urllib.request
from typing import NamedTuple

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings


class ServiceCheck(NamedTuple):
    name: str
    host: str
    port: int
    url: str | None = None


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check whether a TCP port is open and reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def check_http_endpoint(url: str, timeout: float = 2.0) -> bool:
    """Check whether an HTTP endpoint is reachable."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 404)
    except Exception:
        return False


def run_checks() -> dict[str, bool]:
    """Verify connectivity to all backing services."""
    settings = get_settings()

    checks = [
        ServiceCheck(
            name="PostgreSQL",
            host=settings.postgres_host,
            port=settings.postgres_port,
        ),
        ServiceCheck(
            name="Redis",
            host=settings.redis_host,
            port=settings.redis_port,
        ),
        ServiceCheck(
            name="Qdrant",
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            url=f"{settings.qdrant_url}/readyz" if settings.qdrant_url else None,
        ),
        ServiceCheck(
            name="Ollama",
            host=settings.ollama_host,
            port=settings.ollama_port,
            url=f"{settings.ollama_base_url}/api/tags" if settings.ollama_base_url else None,
        ),
    ]

    results = {}
    print("=" * 60)
    print("Backing Services Connectivity Check")
    print("=" * 60)

    for service in checks:
        tcp_ok = check_tcp_port(service.host, service.port)
        http_ok = check_http_endpoint(service.url) if service.url else None

        reachable = tcp_ok or (http_ok is True)
        results[service.name] = reachable
        status_str = "REACHABLE" if reachable else "UNREACHABLE (service down or stopped)"
        print(f"[{'PASS' if reachable else 'FAIL'}] {service.name:<12} ({service.host}:{service.port}) -> {status_str}")

    print("=" * 60)
    return results


if __name__ == "__main__":
    results = run_checks()
    all_ok = all(results.values())
    if not all_ok:
        print("\nNote: Some services are unreachable. Start them with: docker compose up -d")
    sys.exit(0 if all_ok else 1)
