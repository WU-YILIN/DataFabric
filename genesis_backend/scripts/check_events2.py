import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"

async def check():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT id, code, name FROM tracking_events ORDER BY id DESC LIMIT 10"))
        print('Discovered events:', res.fetchall())
    await engine.dispose()

asyncio.run(check())
