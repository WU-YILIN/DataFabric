import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"

async def check():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT id, status, error_message FROM pipelines ORDER BY id DESC LIMIT 5"))
        print(res.fetchall())
    await engine.dispose()

asyncio.run(check())
