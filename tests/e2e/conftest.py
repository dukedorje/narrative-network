"""E2E test fixtures — target any deployment via E2E_BASE_URL.

Usage:
    E2E_BASE_URL=https://futograph.online     (prod — routes via SvelteKit proxy)
    E2E_BASE_URL=http://localhost:8080         (gateway direct)
"""

import os

import httpx
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests unless E2E_BASE_URL is set."""
    if not os.environ.get("E2E_BASE_URL"):
        skip = pytest.mark.skip(reason="E2E_BASE_URL not set")
        for item in items:
            item.add_marker(skip)


@pytest.fixture
def base_url() -> str:
    return os.environ["E2E_BASE_URL"].rstrip("/")


@pytest.fixture
def is_gateway_direct(base_url: str) -> bool:
    """True when pointing directly at the Python gateway (port 8080)."""
    return ":8080" in base_url


@pytest.fixture
async def client(base_url: str) -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as c:
        yield c


@pytest.fixture
def gw_path(is_gateway_direct: bool):
    """Return a path mapper: direct gateway paths or /gateway/* prefix for prod ingress.

    Direct:  /healthz, /enter, /graph/nodes
    Prod:    /gateway/healthz, /gateway/enter, /gateway/graph/nodes
    """

    def _path(gateway_path: str) -> str:
        if is_gateway_direct:
            return gateway_path
        return f"/gateway{gateway_path}"

    return _path
