"""
IngesterClient — internal HTTP client that keeps the genesis-ingester gateway
in sync with the DataFabric ingestion key lifecycle.

Whenever a channel is created, key-rotated, or deleted in DataFabric,
this client calls the gateway's admin endpoint so the in-memory key store
is updated immediately — no restart required.
"""

import httpx
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# We use a module-level async client so connections are reused (keep-alive).
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.INGESTER_BASE_URL,
            headers={"X-Internal-Key": settings.INGESTER_INTERNAL_KEY},
            timeout=5.0,
        )
    return _client


async def register_key(ingest_key: str) -> None:
    """Tell the gateway to accept a newly-created ingest key."""
    if not settings.INGESTER_BASE_URL:
        logger.debug("INGESTER_BASE_URL not set, skipping gateway key registration")
        return
    try:
        resp = await _get_client().post("/admin/keys", json={"key": ingest_key})
        resp.raise_for_status()
        logger.info("Ingester gateway: key registered", key_prefix=ingest_key[:8])
    except Exception as exc:
        # Non-fatal: key is persisted in Postgres; gateway will pick it up on
        # its next Redis background sync (every 30 s).
        logger.warning("Ingester gateway key registration failed (non-fatal)", error=str(exc))


async def revoke_key(ingest_key: str) -> None:
    """Tell the gateway to stop accepting a revoked ingest key."""
    if not settings.INGESTER_BASE_URL:
        return
    try:
        resp = await _get_client().request("DELETE", "/admin/keys", json={"key": ingest_key})
        resp.raise_for_status()
        logger.info("Ingester gateway: key revoked", key_prefix=ingest_key[:8])
    except Exception as exc:
        logger.warning("Ingester gateway key revocation failed (non-fatal)", error=str(exc))


async def rotate_key(old_key: str, new_key: str) -> None:
    """Atomically swap an old key for a new one in the gateway."""
    await register_key(new_key)
    await revoke_key(old_key)
