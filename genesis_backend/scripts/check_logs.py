import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"

async def check():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT COUNT(*) FROM ingestion_event_logs"))
        print('Total logs:', res.fetchone()[0])
        res = await conn.execute(text("SELECT * FROM ingestion_event_logs ORDER BY id DESC LIMIT 1"))
        print('Latest log:', res.fetchone())
    await engine.dispose()

asyncio.run(check())
