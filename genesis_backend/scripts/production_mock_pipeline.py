import json
import time
import uuid
import threading
import requests
import redis
from datetime import datetime
from sqlalchemy import create_engine, text

POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/genesis_db"
KAFKA_BROKER = "localhost:9092"
INGESTER_URL = "http://localhost:8090/v1/ingest"
REDIS_URL = "redis://localhost:6379/0"

engine = create_engine(POSTGRES_URL)

import os
import sys
# Add project root to sys.path to allow imports from src
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import Session
from src.infrastructure.database.models.tenant import Tenant
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.ingestion_channel_config import IngestionChannelConfig
from src.infrastructure.database.models.event import TrackingEvent

def init_db_metadata():
    """Initialize DB with necessary Tenant, Project, Channel, and Contract fields"""
    with Session(engine) as session:
        # 1. Tenant
        tenant = session.query(Tenant).filter_by(slug='mock_acme').first()
        if not tenant:
            tenant = Tenant(name='Mock ACME', slug='mock_acme', status='ACTIVE')
            session.add(tenant)
            session.commit()
            
        # 2. Project
        project_key = "mock-prod-key-12345"
        project = session.query(Project).filter_by(api_key=project_key).first()
        if not project:
            project = Project(
                id=1,
                tenant_id=tenant.id, name='Production Mock Project', 
                description='Mocked', api_key=project_key,
                tags=[], tech_stack={}
            )
            session.add(project)
            session.commit()
            
        # 3. Channel Config
        channel = session.query(IngestionChannelConfig).filter_by(app_id='app123').first()
        if not channel:
            channel = IngestionChannelConfig(
                tenant_id=tenant.id, project_id=project.id,
                platform='web', app_name='mock_app', environment='prod',
                app_id='app123', ingest_key='ingest123',
                endpoint_domain='localhost', created_by='sys', updated_by='sys',
                status='ACTIVE'
            )
            session.add(channel)
            session.commit()
            
        # 4. Tracking Event
        evt = session.query(TrackingEvent).filter_by(project_id=project.id, code='checkout').first()
        props_dict = {
            "event": {"type": "STRING", "description": "System event name"},
            "user_id": {"type": "INT", "description": "The user ID"},
            "price": {"type": "FLOAT", "description": "The item price"},
        }
        if not evt:
            evt = TrackingEvent(
                project_id=project.id, name='Checkout Event', code='checkout',
                domain='commerce', properties=props_dict, status='ACTIVE',
                tags=[]
            )
            session.add(evt)
        else:
            evt.properties = props_dict
        session.commit()
        
        return tenant.id, project.id, channel.id, project_key


def traffic_generator(project_key: str):
    """Sends JSON payloads continuously to the Golang Ingester"""
    print(f"[TrafficGen] Starting traffic generator on {INGESTER_URL}...")
    headers = {"X-Project-Key": project_key, "Content-Type": "application/json"}
    
    # Wait a bit for the kafka consumer to be ready
    time.sleep(2)
    
    count = 0
    while True:
        payload = {
            "event": "checkout",
            "user_id": 1000 + count,
            # 'price' is standard, but here it's missing or we inject unknown fields
            "zhifu_jine": 99.50 + count,
            "yonghu_id": f"u_{1000+count}"
        }
        try:
            res = requests.post(INGESTER_URL, headers=headers, json=payload, timeout=2)
            if res.status_code == 204:
                print(f"[TrafficGen] Successfully sent event {count} -> {payload}")
            else:
                print(f"[TrafficGen] Failed to send: {res.status_code} {res.text}")
        except Exception as e:
            print(f"[TrafficGen] Request error: {e}")
            
        count += 1
        time.sleep(3)


def kafka_sink(tenant_id, project_id, channel_id, project_key):
    """Consumes from Kafka and writes to PostgreSQL (simulating Flink/Celery Pipeline)"""
    from kafka import KafkaConsumer
    print(f"[KafkaSink] Connecting to Kafka {KAFKA_BROKER}...")
    consumer = KafkaConsumer(
        'ods_raw_events',
        bootstrap_servers=[KAFKA_BROKER],
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id='genesis-mock-production-sink',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    print(f"[KafkaSink] Listening to 'ods_raw_events'...")
    
    # Ensure raw table exists before sinking
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ods_raw_events (
                id          SERIAL PRIMARY KEY,
                server_time TEXT,
                project_key TEXT,
                remote_ip   TEXT,
                raw_payload JSONB
            )
        """))
    
    for message in consumer:
        envelope = message.value
        # envelope has: _uuid, _server_time, _project_key, _remote_ip, raw_payload
        raw_payload = envelope.get("raw_payload", {})
        event_name = raw_payload.get("event", "unknown")
        
        with engine.begin() as conn:
            # Insert into ods_raw_events
            conn.execute(text(
                "INSERT INTO ods_raw_events (server_time, project_key, remote_ip, raw_payload) "
                "VALUES (:st, :pk, :ip, :rp)"
            ), {
                "st": envelope.get("_server_time"),
                "pk": envelope.get("_project_key"),
                "ip": envelope.get("_remote_ip"),
                "rp": json.dumps(raw_payload)
            })

            # Insert into ingestion_event_logs (for AI discovery scanning)
            conn.execute(text(
                "INSERT INTO ingestion_event_logs (tenant_id, project_id, channel_id, request_id, event_name, event_ts, status, payload, created_at, updated_at) "
                "VALUES (:t_id, :p_id, :c_id, :req, :evt, NOW(), 'SUCCESS', :pl, NOW(), NOW())"
            ), {
                "t_id": tenant_id, "p_id": project_id, "c_id": channel_id,
                "req": envelope.get("_uuid", str(uuid.uuid4())),
                "evt": event_name,
                "pl": json.dumps(raw_payload)
            })
            
        print(f"[KafkaSink] Flushed 1 event (UUID: {envelope.get('_uuid')}) into PostgreSQL")


if __name__ == "__main__":
    t_id, p_id, c_id, p_key = init_db_metadata()
    print("[Main] Initialized database mock metadata successfully.")
    
    # Push key to Redis for Go Ingester auth
    print("[Main] Pushing project_key to Redis so genesis_ingester accepts it...")
    try:
        r = redis.from_url(REDIS_URL)
        r.sadd("datafabric:api_keys", p_key)
        print("[Main] Redis keys synced.")
    except Exception as e:
        print(f"[Main] Failed to sync Redis (make sure it's running): {e}")
        
    # Wait for the Go Ingester to do its background sync
    print("[Main] Waiting 5 seconds for Ingester to sync from Redis...")
    time.sleep(5)
    
    # Run Traffic Gen
    t = threading.Thread(target=traffic_generator, args=(p_key,), daemon=True)
    t.start()
    
    # Run Kafka Sink (blocks main thread)
    kafka_sink(t_id, p_id, c_id, p_key)
