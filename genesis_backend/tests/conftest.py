import pytest
import asyncio
from typing import AsyncGenerator
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.config import settings
from src.app import app
from src.infrastructure.database.session import engine

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def app_lifespan():
    settings.PIPELINE_AUTO_SYNC_ENABLED = False
    settings.SOURCE_INTAKE_WATCH_ENABLED = False
    await app.router.startup()
    try:
        yield
    finally:
        await app.router.shutdown()
        await engine.dispose()

@pytest_asyncio.fixture
async def client(app_lifespan) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
