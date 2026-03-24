import subprocess
import time
from typing import Any

import boto3
import pytest
from httpx import AsyncClient
from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from pymongo import MongoClient


MONGO_CONTAINER = "datafabric_mongo_mock"
MONGO_PORT = 27018
MINIO_CONTAINER = "datafabric_minio_mock"
MINIO_PORT = 9000
KAFKA_CONTAINER = "datafabric_redpanda_mock"
KAFKA_PORT = 19092
KAFKA_BOOTSTRAP = f"127.0.0.1:{KAFKA_PORT}"


def _context_headers(access_token: str, context: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


async def _register_context(client: AsyncClient, prefix: str) -> dict[str, Any]:
    suffix = str(int(time.time() * 1000))
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"{prefix}-{suffix}",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return {"headers": _context_headers(data["access_token"], data["default_context"]), "suffix": suffix}


def _ensure_mongo() -> None:
    _docker("rm", "-f", MONGO_CONTAINER, check=False)
    _docker("run", "-d", "--name", MONGO_CONTAINER, "-p", f"{MONGO_PORT}:27017", "mongo:7")
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            client = MongoClient(f"mongodb://127.0.0.1:{MONGO_PORT}", serverSelectionTimeoutMS=2000)
            try:
                client.admin.command("ping")
                database = client["fabric_non_sql"]
                database["events"].insert_many(
                    [
                        {"event_id": "evt_1", "user_id": "u_1", "created_at": "2026-03-22T10:00:00Z"},
                        {"event_id": "evt_2", "user_id": "u_2", "created_at": "2026-03-22T10:01:00Z"},
                    ]
                )
                return
            finally:
                client.close()
        except Exception:
            time.sleep(2)
    raise RuntimeError("MongoDB mock did not become ready in time")


def _mutate_mongo() -> None:
    client = MongoClient(f"mongodb://127.0.0.1:{MONGO_PORT}", serverSelectionTimeoutMS=2000)
    try:
        db = client["fabric_non_sql"]
        db["profiles"].insert_many(
            [
                {"profile_id": "p_1", "city": "Shanghai"},
                {"profile_id": "p_2", "city": "Hangzhou"},
            ]
        )
        db["events"].insert_one({"event_id": "evt_3", "user_id": "u_3", "created_at": "2026-03-22T10:02:00Z", "channel": "web"})
    finally:
        client.close()


def _cleanup_mongo() -> None:
    _docker("rm", "-f", MONGO_CONTAINER, check=False)


def _minio_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{MINIO_PORT}",
        aws_access_key_id="minio",
        aws_secret_access_key="minio12345",
        region_name="us-east-1",
    )


def _ensure_minio() -> None:
    _docker("rm", "-f", MINIO_CONTAINER, check=False)
    _docker(
        "run",
        "-d",
        "--name",
        MINIO_CONTAINER,
        "-p",
        f"{MINIO_PORT}:9000",
        "-e",
        "MINIO_ROOT_USER=minio",
        "-e",
        "MINIO_ROOT_PASSWORD=minio12345",
        "minio/minio",
        "server",
        "/data",
    )
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            client = _minio_client()
            client.list_buckets()
            bucket = "fabric-bucket"
            existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
            client.put_object(Bucket=bucket, Key="orders/2026-03-22/orders.parquet", Body=b"parquet-sample")
            client.put_object(Bucket=bucket, Key="users/2026-03-22/users.json", Body=b'{"id":"u_1"}')
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("MinIO mock did not become ready in time")


def _mutate_minio() -> None:
    client = _minio_client()
    client.put_object(Bucket="fabric-bucket", Key="inventory/2026-03-22/inventory.csv", Body=b"sku,stock\nsku_1,12\n")


def _cleanup_minio() -> None:
    _docker("rm", "-f", MINIO_CONTAINER, check=False)


def _ensure_kafka() -> None:
    _docker("rm", "-f", KAFKA_CONTAINER, check=False)
    _docker(
        "run",
        "-d",
        "--name",
        KAFKA_CONTAINER,
        "-p",
        f"{KAFKA_PORT}:19092",
        "redpandadata/redpanda:v24.1.13",
        "redpanda",
        "start",
        "--overprovisioned",
        "--smp",
        "1",
        "--memory",
        "512M",
        "--reserve-memory",
        "0M",
        "--node-id",
        "0",
        "--check=false",
        "--kafka-addr",
        "PLAINTEXT://0.0.0.0:19092",
        "--advertise-kafka-addr",
        f"PLAINTEXT://127.0.0.1:{KAFKA_PORT}",
    )
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                request_timeout_ms=5000,
                api_version_auto_timeout_ms=5000,
                consumer_timeout_ms=1000,
            )
            try:
                consumer.topics()
            finally:
                consumer.close()
            return
        except Exception:
            time.sleep(3)
    raise RuntimeError("Kafka mock did not become ready in time")


def _create_topic(name: str) -> None:
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, request_timeout_ms=5000, api_version_auto_timeout_ms=5000)
    try:
        existing = set(admin.list_topics())
        if name not in existing:
            admin.create_topics([NewTopic(name=name, num_partitions=2, replication_factor=1)])
    finally:
        admin.close()


def _cleanup_kafka() -> None:
    _docker("rm", "-f", KAFKA_CONTAINER, check=False)


@pytest.mark.asyncio
async def test_source_intake_mongodb_discover_watch_and_memory(client: AsyncClient):
    _ensure_mongo()
    try:
        context = await _register_context(client, "it_source_intake_mongo")
        headers = context["headers"]

        create_resp = await client.post(
            "/api/v1/source-intake/instances",
            headers=headers,
            json={
                "instance_name": "mongo_instance",
                "connector_key": "mongodb",
                "config": {"uri": f"mongodb://127.0.0.1:{MONGO_PORT}", "database": "fabric_non_sql", "memory_scope_default": "PRIVATE"},
            },
        )
        assert create_resp.status_code == 200
        instance_id = create_resp.json()["data"]["id"]

        assert (await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)).status_code == 200
        discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
        assert discover_resp.status_code == 200
        assets = discover_resp.json()["data"]["discovery"]["assets"]
        assert any(item["asset_type"] == "COLLECTION" and item["qualified_name"].endswith(".events") for item in assets)

        _mutate_mongo()
        watch_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/watch/run", headers=headers)
        assert watch_resp.status_code == 200
        assert watch_resp.json()["data"]["changes"]

        candidates_resp = await client.get("/api/v1/source-intake/candidates", headers=headers, params={"page": 1, "page_size": 50, "status": "OPEN"})
        assert candidates_resp.status_code == 200
        candidate_id = candidates_resp.json()["data"]["items"][0]["id"]

        share_resp = await client.post(f"/api/v1/source-intake/candidates/{candidate_id}/share", headers=headers)
        assert share_resp.status_code == 200

        memory_resp = await client.get("/api/v1/knowledge/documents", headers=headers, params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0})
        assert memory_resp.status_code == 200
        memory_items = memory_resp.json()["data"]["items"]
        assert any(item["title"] == "[Source Memory] mongo_instance" for item in memory_items)
        assert any("shared-memory" in item["tags"] for item in memory_items)
    finally:
        _cleanup_mongo()


@pytest.mark.asyncio
async def test_source_intake_s3_discover_watch_and_memory(client: AsyncClient):
    _ensure_minio()
    try:
        context = await _register_context(client, "it_source_intake_s3")
        headers = context["headers"]

        create_resp = await client.post(
            "/api/v1/source-intake/instances",
            headers=headers,
            json={
                "instance_name": "minio_instance",
                "connector_key": "s3",
                "config": {
                    "endpoint_url": f"http://127.0.0.1:{MINIO_PORT}",
                    "region_name": "us-east-1",
                    "access_key_id": "minio",
                    "secret_access_key": "minio12345",
                    "bucket": "fabric-bucket",
                    "prefix": "",
                    "memory_scope_default": "PRIVATE",
                },
            },
        )
        assert create_resp.status_code == 200
        instance_id = create_resp.json()["data"]["id"]

        assert (await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)).status_code == 200
        discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
        assert discover_resp.status_code == 200
        assets = discover_resp.json()["data"]["discovery"]["assets"]
        assert any(item["asset_type"] == "OBJECT" and item["qualified_name"].endswith("orders.parquet") for item in assets)

        _mutate_minio()
        watch_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/watch/run", headers=headers)
        assert watch_resp.status_code == 200

        candidates_resp = await client.get("/api/v1/source-intake/candidates", headers=headers, params={"page": 1, "page_size": 50, "status": "OPEN"})
        assert candidates_resp.status_code == 200
        candidate_id = candidates_resp.json()["data"]["items"][0]["id"]

        promote_resp = await client.post(f"/api/v1/source-intake/candidates/{candidate_id}/promote", headers=headers)
        assert promote_resp.status_code == 200

        memory_resp = await client.get("/api/v1/knowledge/documents", headers=headers, params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0})
        assert memory_resp.status_code == 200
        memory_items = memory_resp.json()["data"]["items"]
        assert any(item["title"] == "[Source Memory] minio_instance" for item in memory_items)
    finally:
        _cleanup_minio()


@pytest.mark.asyncio
async def test_source_intake_kafka_discover_watch_and_memory(client: AsyncClient):
    _ensure_kafka()
    try:
        context = await _register_context(client, "it_source_intake_kafka")
        headers = context["headers"]

        base_topic = f"fabric_topic_{context['suffix']}"
        added_topic = f"fabric_topic_added_{context['suffix']}"
        _create_topic(base_topic)

        create_resp = await client.post(
            "/api/v1/source-intake/instances",
            headers=headers,
            json={
                "instance_name": "kafka_instance",
                "connector_key": "kafka",
                "config": {"bootstrap_servers": KAFKA_BOOTSTRAP, "security_protocol": "PLAINTEXT", "memory_scope_default": "PRIVATE"},
            },
        )
        assert create_resp.status_code == 200
        instance_id = create_resp.json()["data"]["id"]

        assert (await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)).status_code == 200
        discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
        assert discover_resp.status_code == 200
        assets = discover_resp.json()["data"]["discovery"]["assets"]
        assert any(item["asset_type"] == "TOPIC" and item["qualified_name"] == base_topic for item in assets)

        _create_topic(added_topic)
        watch_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/watch/run", headers=headers)
        assert watch_resp.status_code == 200

        candidates_resp = await client.get("/api/v1/source-intake/candidates", headers=headers, params={"page": 1, "page_size": 50, "status": "OPEN"})
        assert candidates_resp.status_code == 200
        candidate_id = candidates_resp.json()["data"]["items"][0]["id"]

        promote_resp = await client.post(f"/api/v1/source-intake/candidates/{candidate_id}/promote", headers=headers)
        assert promote_resp.status_code == 200

        memory_resp = await client.get("/api/v1/knowledge/documents", headers=headers, params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0})
        assert memory_resp.status_code == 200
        memory_items = memory_resp.json()["data"]["items"]
        assert any(item["title"] == "[Source Memory] kafka_instance" for item in memory_items)
    finally:
        _cleanup_kafka()


@pytest.mark.asyncio
async def test_source_intake_csv_discover_watch_and_memory(client: AsyncClient, tmp_path):
    context = await _register_context(client, "it_source_intake_csv")
    headers = context["headers"]

    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("order_id,amount\nord_1,12\nord_2,18\n", encoding="utf-8")

    create_resp = await client.post(
        "/api/v1/source-intake/instances",
        headers=headers,
        json={
            "instance_name": "csv_instance",
            "connector_key": "csv",
            "config": {
                "path": str(csv_path),
                "delimiter": ",",
                "encoding": "utf-8",
                "has_header": "true",
                "memory_scope_default": "PRIVATE",
            },
        },
    )
    assert create_resp.status_code == 200
    instance_id = create_resp.json()["data"]["id"]

    test_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)
    assert test_resp.status_code == 200

    discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
    assert discover_resp.status_code == 200
    assets = discover_resp.json()["data"]["discovery"]["assets"]
    assert any(item["asset_type"] == "FILE" and item["qualified_name"].endswith("orders.csv") for item in assets)

    csv_path.write_text("order_id,amount\nord_1,12\nord_2,18\nord_3,21\n", encoding="utf-8")

    watch_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/watch/run", headers=headers)
    assert watch_resp.status_code == 200
    assert watch_resp.json()["data"]["changes"]

    candidates_resp = await client.get(
        "/api/v1/source-intake/candidates",
        headers=headers,
        params={"page": 1, "page_size": 50, "status": "OPEN"},
    )
    assert candidates_resp.status_code == 200
    candidate_items = candidates_resp.json()["data"]["items"]
    target = next(item for item in candidate_items if item["instance_id"] == instance_id)

    promote_resp = await client.post(f"/api/v1/source-intake/candidates/{target['id']}/promote", headers=headers)
    assert promote_resp.status_code == 200

    memory_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0},
    )
    assert memory_resp.status_code == 200
    memory_items = memory_resp.json()["data"]["items"]
    assert any(item["title"] == "[Source Memory] csv_instance" for item in memory_items)
