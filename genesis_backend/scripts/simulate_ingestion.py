import asyncio
import httpx
import uuid
import time
import random
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"
API_URL = "http://127.0.0.1:8000/api/v1/ingestion/gateway/events"

async def get_active_channel():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT ingest_key, app_id FROM ingestion_channel_configs WHERE status='ACTIVE' LIMIT 1"))
        row = res.fetchone()
    await engine.dispose()
    return row

async def main():
    channel = await get_active_channel()
    if not channel:
        print("❌ No active ingestion channel found. Please create one in the UI first.")
        return

    ingest_key, app_id = channel
    print(f"✅ Found active channel (app_id: {app_id}, key: {ingest_key[:8]}...)")

    # The event_name must follow namespace.action format (e.g., user.signup)
    # The requirement regex is ^[a-z]+(\.[a-z0-9_]+)+$
    event_names = ["user.signup", "user.login", "page.view", "item.purchase"]

    async with httpx.AsyncClient() as client:
        print("🚀 Starting mock data ingestion (press Ctrl+C to stop)...")
        count = 0
        try:
            while True:
                event_name = random.choice(event_names)
                payload = {
                    "event_name": event_name,
                    "app_id": app_id,
                    "event_ts": datetime.now(timezone.utc).isoformat(),
                    "properties": {
                        "user_id": f"u_{random.randint(1000, 9999)}",
                        "session_id": str(uuid.uuid4()),
                        "platform": random.choice(["web", "ios", "android"])
                    }
                }

                if event_name == "item.purchase":
                    payload["properties"]["amount"] = round(random.uniform(10.0, 500.0), 2)
                    payload["properties"]["currency"] = "USD"
                    payload["properties"]["item_id"] = f"item_{random.randint(1, 100)}"

                headers = {
                    "X-INGEST-KEY": ingest_key,
                    "Content-Type": "application/json"
                }

                resp = await client.post(API_URL, json=payload, headers=headers)
                
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("data", {}).get("status")
                    print(f"[{count}] Sent {event_name.ljust(15)} -> HTTP 200 (Status: {status})")
                else:
                    print(f"[{count}] Error {resp.status_code}: {resp.text}")

                count += 1
                await asyncio.sleep(random.uniform(0.5, 2.0))

        except KeyboardInterrupt:
            print(f"\n🛑 Stopped! Sent {count} events.")

if __name__ == "__main__":
    asyncio.run(main())
