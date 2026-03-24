import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"

async def main():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE governance_checks ALTER COLUMN recommended_code TYPE TEXT"))
        await conn.execute(text("ALTER TABLE governance_checks ALTER COLUMN reasoning TYPE TEXT"))
        print("OK: governance_checks columns altered to TEXT")
    await engine.dispose()

asyncio.run(main())
