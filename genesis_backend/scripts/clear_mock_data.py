import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/genesis_db"

async def clear_mock_data():
    engine = create_async_engine(DB_URL)
    
    # We must delete child tables first, then parent tables.
    tables_to_delete = [
        "schema_field_mappings",      # Depends on tracking_events
        "governance_checks",          # Depends on tracking_events
        "pipeline_status_history",    # Depends on pipeline_histories and pipelines
        "pipeline_histories",         # Depends on pipelines
        "pipelines",                  # Depends on tracking_events
        "event_change_logs",          # Depends on tracking_events
        "ingestion_event_logs",       # Independent log table
        "alerts",                     # Independent alerts
        "audit_logs",                 # Independent audit logs
        "tracking_events"             # Parent event table
    ]
    
    print("🗑️  Starting safe cleanup...")
    
    async with engine.begin() as conn:
        await conn.execute(text("""
            UPDATE ingestion_channel_configs 
            SET accepted_events_count = 0, 
                rejected_events_count = 0, 
                last_seen_at = NULL, 
                last_event_at = NULL
        """))
        print("✅ Reset ingestion channel counters")
        
    for table in tables_to_delete:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"DELETE FROM {table}"))
            print(f"✅ Cleared {table}")
        except Exception as e:
            print(f"⚠️ Failed to clear {table}: {e}")
            
    # Reset sequences
    for table in tables_to_delete:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER SEQUENCE IF EXISTS {table}_id_seq RESTART WITH 1;"))
        except Exception:
            pass
            
    print("\n✨ Data cleanup complete!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_mock_data())
