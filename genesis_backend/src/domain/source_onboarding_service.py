import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiomysql
import asyncpg
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.settings import decrypt_mapping, encrypt_mapping
from src.infrastructure.database.models.external_data_source import ExternalDataSource
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.repositories.base import BaseRepository


SUPPORTED_SOURCE_TYPES = {"POSTGRESQL", "MYSQL", "SQLITE"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask_config(source_type: str, config: dict[str, Any]) -> dict[str, Any]:
    masked = dict(config)
    secret_fields = {"password"}
    for field in secret_fields:
        if field in masked and masked[field]:
            masked[field] = "***"
    if source_type == "SQLITE" and masked.get("file_path"):
        masked["file_path"] = str(masked["file_path"])
    return masked


def _merge_config_with_existing(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "password":
            # The frontend edits masked source details and will often send "***"
            # back during a generic save. Preserve the original secret unless the
            # user actually supplied a new password.
            if value in (None, "", "***"):
                continue
        merged[key] = value
    return merged


def _mysql_value(row: dict[str, Any], key: str) -> Any:
    return row.get(key) if key in row else row.get(key.upper())


class SourceOnboardingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = BaseRepository(ExternalDataSource, db)

    async def list_sources(
        self,
        project_id: int,
        *,
        q: str | None = None,
        source_type: str | None = None,
        status: str | None = None,
        heat: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        filters = [ExternalDataSource.project_id == project_id]
        if q and q.strip():
            keyword = f"%{q.strip()}%"
            filters.append(
                or_(
                    ExternalDataSource.source_name.ilike(keyword),
                    ExternalDataSource.source_type.ilike(keyword),
                )
            )
        if source_type and source_type.strip().upper() != "ALL":
            filters.append(ExternalDataSource.source_type == source_type.strip().upper())
        if status and status.strip().upper() != "ALL":
            filters.append(ExternalDataSource.status == status.strip().upper())

        result = await self.db.execute(
            select(ExternalDataSource)
            .where(*filters)
            .order_by(ExternalDataSource.updated_at.desc(), ExternalDataSource.id.desc())
        )
        serialized_items = [self._serialize_source(item) for item in result.scalars().all()]
        if heat and heat.strip().upper() != "ALL":
            normalized_heat = heat.strip().upper()
            serialized_items = [
                item for item in serialized_items if str(item.get("heat_level") or "").upper() == normalized_heat
            ]

        total = len(serialized_items)
        total_pages = max((total + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages)
        start = (current_page - 1) * page_size
        end = start + page_size
        items = serialized_items[start:end]
        return {
            "items": items,
            "total": total,
            "page": current_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "supported_source_types": sorted(SUPPORTED_SOURCE_TYPES),
        }

    async def get_source(self, project_id: int, source_id: int) -> dict[str, Any]:
        source = await self._get_project_source(project_id, source_id)
        return self._serialize_source(source, include_discovery=True)

    async def create_source(
        self,
        project_id: int,
        source_name: str,
        source_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_type = self._normalize_source_type(source_type)
        source = await self.repo.create(
            {
                "project_id": project_id,
                "source_name": source_name.strip(),
                "source_type": normalized_type,
                "status": "DRAFT",
                "encrypted_config": encrypt_mapping(config),
                "discovery_payload": {},
            }
        )
        return self._serialize_source(source)

    async def update_source(
        self,
        project_id: int,
        source_id: int,
        *,
        source_name: str | None,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        source = await self._get_project_source(project_id, source_id)
        payload: dict[str, Any] = {}
        if source_name is not None:
            payload["source_name"] = source_name.strip()
        if config is not None:
            existing_config = decrypt_mapping(source.encrypted_config)
            merged_config = _merge_config_with_existing(existing_config, config)
            payload["encrypted_config"] = encrypt_mapping(merged_config)
            payload["status"] = "DRAFT"
        source = await self.repo.update(source, payload)
        return self._serialize_source(source)

    async def delete_source(self, project_id: int, source_id: int) -> dict[str, Any]:
        source = await self._get_project_source(project_id, source_id)
        await self.repo.remove(source.id)
        await self.db.commit()
        return {
            "id": source_id,
            "source_name": source.source_name,
            "deleted": True,
        }

    async def test_connection(self, project_id: int, source_id: int) -> dict[str, Any]:
        source = await self._get_project_source(project_id, source_id)
        config = decrypt_mapping(source.encrypted_config)

        try:
            message = await self._run_connection_test(source.source_type, config)
            source = await self.repo.update(
                source,
                {
                    "status": "CONNECTED",
                    "last_test_status": "SUCCESS",
                    "last_test_message": message,
                    "last_tested_at": _utcnow(),
                },
            )
            return {
                "status": "SUCCESS",
                "message": message,
                "source": self._serialize_source(source),
            }
        except Exception as exc:
            source = await self.repo.update(
                source,
                {
                    "status": "TEST_FAILED",
                    "last_test_status": "FAILURE",
                    "last_test_message": str(exc),
                    "last_tested_at": _utcnow(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": str(exc), "source": self._serialize_source(source)},
            ) from exc

    async def scan_source(self, project_id: int, source_id: int) -> dict[str, Any]:
        return await self.scan_source_with_memory(project_id, source_id, actor_id=None, tenant_id=None, user_id=None)

    async def scan_source_with_memory(
        self,
        project_id: int,
        source_id: int,
        *,
        actor_id: str | None,
        tenant_id: int | None,
        user_id: int | None,
    ) -> dict[str, Any]:
        source = await self._get_project_source(project_id, source_id)
        config = decrypt_mapping(source.encrypted_config)
        try:
            discovery = await self._run_scan(source.source_type, config)
            source = await self.repo.update(
                source,
                {
                    "status": "OBSERVED",
                    "discovery_payload": discovery,
                    "last_scan_status": "SUCCESS",
                    "last_scan_message": f"Discovered {len(discovery.get('objects', []))} objects",
                    "last_scanned_at": _utcnow(),
                },
            )
            await self._sync_memory_document(
                source=source,
                discovery=discovery,
                actor_id=actor_id,
                tenant_id=tenant_id,
                user_id=user_id,
                memory_scope=str(config.get("memory_scope") or "PRIVATE").upper(),
            )
            return {
                "source": self._serialize_source(source, include_discovery=True),
                "discovery": discovery,
            }
        except Exception as exc:
            source = await self.repo.update(
                source,
                {
                    "status": "SCAN_FAILED",
                    "last_scan_status": "FAILURE",
                    "last_scan_message": str(exc),
                    "last_scanned_at": _utcnow(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": str(exc), "source": self._serialize_source(source)},
            ) from exc

    def _serialize_source(self, source: ExternalDataSource, *, include_discovery: bool = False) -> dict[str, Any]:
        discovery = source.discovery_payload or {}
        objects = discovery.get("objects", []) if isinstance(discovery, dict) else []
        total_rows = sum(int(item.get("row_count_estimate") or 0) for item in objects)
        total_columns = sum(int(item.get("column_count") or 0) for item in objects)
        estimated_bytes = total_rows * max(total_columns, 1) * 48
        payload = {
            "id": source.id,
            "source_name": source.source_name,
            "source_type": source.source_type,
            "status": source.status,
            "heat_level": self._heat_level(total_rows),
            "total_objects": len(objects),
            "total_rows": total_rows,
            "estimated_bytes": estimated_bytes,
            "config": _mask_config(source.source_type, decrypt_mapping(source.encrypted_config)),
            "last_test_status": source.last_test_status,
            "last_test_message": source.last_test_message,
            "last_tested_at": source.last_tested_at.isoformat() if source.last_tested_at else None,
            "last_scan_status": source.last_scan_status,
            "last_scan_message": source.last_scan_message,
            "last_scanned_at": source.last_scanned_at.isoformat() if source.last_scanned_at else None,
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }
        if include_discovery:
            payload["discovery"] = source.discovery_payload or {}
        return payload

    async def _get_project_source(self, project_id: int, source_id: int) -> ExternalDataSource:
        source = await self.repo.get(source_id)
        if source is None or source.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return source

    def _normalize_source_type(self, source_type: str) -> str:
        normalized = source_type.strip().upper()
        if normalized not in SUPPORTED_SOURCE_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported source type")
        return normalized

    async def _run_connection_test(self, source_type: str, config: dict[str, Any]) -> str:
        if source_type == "POSTGRESQL":
            conn = await asyncpg.connect(
                host=str(config.get("host", "localhost")),
                port=int(config.get("port", 5432)),
                user=str(config.get("username", "")),
                password=str(config.get("password", "")),
                database=str(config.get("database", "")),
            )
            try:
                await conn.fetchval("select 1")
            finally:
                await conn.close()
            return "PostgreSQL connection succeeded"

        if source_type == "SQLITE":
            file_path = Path(str(config.get("file_path", "")).strip())
            if not file_path.exists():
                raise ValueError(f"SQLite file not found: {file_path}")
            await asyncio.to_thread(self._sqlite_test, file_path)
            return "SQLite connection succeeded"

        if source_type == "MYSQL":
            conn = await aiomysql.connect(
                host=str(config.get("host", "localhost")),
                port=int(config.get("port", 3306)),
                user=str(config.get("username", "")),
                password=str(config.get("password", "")),
                db=str(config.get("database", "")),
                autocommit=True,
            )
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("select 1")
                    await cursor.fetchone()
            finally:
                conn.close()
            return "MySQL connection succeeded"

        raise ValueError("Unsupported source type")

    async def _run_scan(self, source_type: str, config: dict[str, Any]) -> dict[str, Any]:
        if source_type == "POSTGRESQL":
            return await self._scan_postgresql(config)
        if source_type == "SQLITE":
            return await asyncio.to_thread(self._scan_sqlite, Path(str(config.get("file_path", "")).strip()))
        if source_type == "MYSQL":
            return await self._scan_mysql(config)
        raise ValueError("Unsupported source type")

    async def _scan_postgresql(self, config: dict[str, Any]) -> dict[str, Any]:
        schema_name = str(config.get("schema", "public") or "public")
        conn = await asyncpg.connect(
            host=str(config.get("host", "localhost")),
            port=int(config.get("port", 5432)),
            user=str(config.get("username", "")),
            password=str(config.get("password", "")),
            database=str(config.get("database", "")),
        )
        try:
            tables = await conn.fetch(
                """
                select table_schema, table_name
                from information_schema.tables
                where table_schema = $1 and table_type = 'BASE TABLE'
                order by table_name
                limit 25
                """,
                schema_name,
            )

            objects = []
            for row in tables:
                columns = await conn.fetch(
                    """
                    select column_name, data_type, is_nullable
                    from information_schema.columns
                    where table_schema = $1 and table_name = $2
                    order by ordinal_position
                    """,
                    row["table_schema"],
                    row["table_name"],
                )
                count_row = await conn.fetchrow(
                    f'select count(*)::bigint as row_count from "{row["table_schema"]}"."{row["table_name"]}"'
                )
                objects.append(
                    self._build_discovery_object(
                        source_type="POSTGRESQL",
                        schema=row["table_schema"],
                        table_name=row["table_name"],
                        row_count=int(count_row["row_count"] if count_row else 0),
                        columns=[
                            {
                                "name": item["column_name"],
                                "data_type": item["data_type"],
                                "nullable": item["is_nullable"] == "YES",
                            }
                            for item in columns
                        ],
                    )
                )
            return {"source_type": "POSTGRESQL", "schema": schema_name, "objects": objects}
        finally:
            await conn.close()

    def _sqlite_test(self, file_path: Path) -> None:
        conn = sqlite3.connect(str(file_path))
        try:
            conn.execute("select 1")
        finally:
            conn.close()

    async def _scan_mysql(self, config: dict[str, Any]) -> dict[str, Any]:
        database_name = str(config.get("database", "")).strip()
        # In MySQL, schema and database are effectively the same namespace.
        # Use the selected database consistently for discovery to avoid users
        # accidentally pointing scans at an empty schema name.
        schema_name = database_name
        conn = await aiomysql.connect(
            host=str(config.get("host", "localhost")),
            port=int(config.get("port", 3306)),
            user=str(config.get("username", "")),
            password=str(config.get("password", "")),
            db=database_name,
            autocommit=True,
        )
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = %s and table_type = 'BASE TABLE'
                    order by table_name
                    limit 25
                    """,
                    (schema_name,),
                )
                tables = await cursor.fetchall()

                objects = []
                for row in tables:
                    table_name = str(_mysql_value(row, "table_name"))
                    await cursor.execute(
                        """
                        select column_name, data_type, is_nullable
                        from information_schema.columns
                        where table_schema = %s and table_name = %s
                        order by ordinal_position
                        """,
                        (schema_name, table_name),
                    )
                    columns = await cursor.fetchall()
                    await cursor.execute(f"select count(*) as row_count from `{table_name}`")
                    count_row = await cursor.fetchone()
                    objects.append(
                        self._build_discovery_object(
                            source_type="MYSQL",
                            schema=schema_name,
                            table_name=table_name,
                            row_count=int((count_row or {}).get("row_count") or 0),
                            columns=[
                                {
                                    "name": str(_mysql_value(item, "column_name")),
                                    "data_type": str(_mysql_value(item, "data_type")),
                                    "nullable": str(_mysql_value(item, "is_nullable")).upper() == "YES",
                                }
                                for item in columns
                            ],
                        )
                    )
                return {"source_type": "MYSQL", "schema": schema_name, "objects": objects}
        finally:
            conn.close()

    def _scan_sqlite(self, file_path: Path) -> dict[str, Any]:
        if not file_path.exists():
            raise ValueError(f"SQLite file not found: {file_path}")
        conn = sqlite3.connect(str(file_path))
        try:
            tables = conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name limit 25"
            ).fetchall()
            objects = []
            for (table_name,) in tables:
                columns_info = conn.execute(f"pragma table_info('{table_name}')").fetchall()
                row_count = conn.execute(f"select count(*) from '{table_name}'").fetchone()[0]
                objects.append(
                    self._build_discovery_object(
                        source_type="SQLITE",
                        schema="main",
                        table_name=table_name,
                        row_count=int(row_count or 0),
                        columns=[
                            {
                                "name": column[1],
                                "data_type": column[2] or "TEXT",
                                "nullable": not bool(column[3]),
                            }
                            for column in columns_info
                        ],
                    )
                )
            return {"source_type": "SQLITE", "schema": "main", "objects": objects}
        finally:
            conn.close()

    def _build_discovery_object(
        self,
        *,
        source_type: str,
        schema: str,
        table_name: str,
        row_count: int,
        columns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        key_candidates = [column["name"] for column in columns if column["name"].lower() in {"id", f"{table_name}_id", "user_id"}]
        time_candidates = [
            column["name"]
            for column in columns
            if any(token in column["name"].lower() for token in ("time", "date", "created", "updated"))
        ]
        inference_candidates: list[dict[str, Any]] = []
        for column in columns:
            lower_name = column["name"].lower()
            if lower_name.endswith("id") or lower_name == "id":
                inference_candidates.append(
                    {
                        "candidate_type": "IDENTITY_FIELD",
                        "target_field": column["name"],
                        "source_paths": [f"{schema}.{table_name}.{column['name']}"],
                        "confidence_score": 0.91,
                        "field_frequency": max(row_count, 1),
                        "reasoning": f"{column['name']} looks like an identity field in {schema}.{table_name}",
                        "recommended_action": "FAST_REVIEW",
                    }
                )
            elif any(token in lower_name for token in ("time", "date", "created", "updated")):
                inference_candidates.append(
                    {
                        "candidate_type": "TIME_FIELD",
                        "target_field": column["name"],
                        "source_paths": [f"{schema}.{table_name}.{column['name']}"],
                        "confidence_score": 0.82,
                        "field_frequency": max(row_count, 1),
                        "reasoning": f"{column['name']} looks like a time field in {schema}.{table_name}",
                        "recommended_action": "REVIEW",
                    }
                )
        return {
            "source_type": source_type,
            "schema": schema,
            "table_name": table_name,
            "row_count_estimate": row_count,
            "estimated_bytes": row_count * max(len(columns), 1) * 48,
            "heat_level": self._heat_level(row_count),
            "column_count": len(columns),
            "columns": columns,
            "key_candidates": key_candidates,
            "time_candidates": time_candidates,
            "inference_candidates": inference_candidates,
        }

    def _heat_level(self, row_count: int) -> str:
        if row_count >= 1_000_000:
            return "HOT"
        if row_count >= 50_000:
            return "WARM"
        return "COLD"

    async def _sync_memory_document(
        self,
        *,
        source: ExternalDataSource,
        discovery: dict[str, Any],
        actor_id: str | None,
        tenant_id: int | None,
        user_id: int | None,
        memory_scope: str,
    ) -> None:
        objects = discovery.get("objects", []) if isinstance(discovery, dict) else []
        total_rows = sum(int(item.get("row_count_estimate") or 0) for item in objects)
        total_columns = sum(int(item.get("column_count") or 0) for item in objects)
        heat_level = self._heat_level(total_rows)
        title = f"[Source Memory] {source.source_name}"
        summary = (
            f"{source.source_name} ({source.source_type}) scanned {len(objects)} objects, "
            f"{total_columns} columns, estimated {total_rows} rows, heat {heat_level}."
        )
        content_lines = [
            f"# Source Memory: {source.source_name}",
            "",
            f"- Source Type: {source.source_type}",
            f"- Status: {source.status}",
            f"- Object Count: {len(objects)}",
            f"- Estimated Rows: {total_rows}",
            f"- Estimated Columns: {total_columns}",
            f"- Heat Level: {heat_level}",
            f"- Memory Scope: {memory_scope}",
            "",
            "## Objects",
        ]
        for obj in objects:
            content_lines.extend(
                [
                    f"### {obj.get('schema')}.{obj.get('table_name')}",
                    f"- Rows: {obj.get('row_count_estimate', 0)}",
                    f"- Columns: {obj.get('column_count', 0)}",
                    f"- Heat: {obj.get('heat_level', self._heat_level(int(obj.get('row_count_estimate') or 0)))}",
                    f"- Estimated Bytes: {obj.get('estimated_bytes', 0)}",
                    f"- Key Candidates: {', '.join(obj.get('key_candidates', [])) or 'none'}",
                    f"- Time Candidates: {', '.join(obj.get('time_candidates', [])) or 'none'}",
                    "- Column Details:",
                ]
            )
            for column in obj.get("columns", []):
                content_lines.append(
                    f"  - {column.get('name')}: {column.get('data_type')} "
                    f"(nullable={column.get('nullable')})"
                )
            if obj.get("inference_candidates"):
                content_lines.append("- Inference Seeds:")
                for candidate in obj.get("inference_candidates", []):
                    content_lines.append(
                        f"  - {candidate.get('candidate_type')} -> {candidate.get('target_field')} "
                        f"(confidence={candidate.get('confidence_score')}, action={candidate.get('recommended_action')})"
                    )
            content_lines.append("")

        tags = ["source-memory", source.source_type.lower(), heat_level.lower()]
        if memory_scope == "TENANT":
            tags.append("shared-memory")

        repo = BaseRepository(KnowledgeDocument, self.db)
        existing_result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.project_id == source.project_id,
                KnowledgeDocument.module == "SOURCE_MEMORY",
                KnowledgeDocument.doc_type == "SOURCE_METADATA",
                KnowledgeDocument.title == title,
            )
        )
        existing = existing_result.scalar_one_or_none()
        payload = {
            "tenant_id": tenant_id,
            "summary": summary,
            "content": "\n".join(content_lines).strip(),
            "status": "PUBLISHED",
            "tags": tags,
            "related_objects": [
                {
                    "source_type": "DATA_SOURCE",
                    "source_id": str(source.id),
                    "label": source.source_name,
                    "module": "SOURCE_ONBOARDING",
                    "module_route": "/source-onboarding",
                }
            ],
            "meta_payload": {
                "source_id": source.id,
                "source_type": source.source_type,
                "memory_scope": memory_scope,
                "total_rows": total_rows,
                "total_columns": total_columns,
                "heat_level": heat_level,
                "discovery": discovery,
            },
            "last_editor_id": actor_id or f"project:{source.project_id}",
            "last_editor_user_id": user_id,
            "published_at": _utcnow(),
        }
        if existing is None:
            await repo.create(
                {
                    "project_id": source.project_id,
                    "tenant_id": tenant_id,
                    "doc_type": "SOURCE_METADATA",
                    "module": "SOURCE_MEMORY",
                    "title": title,
                    "format": "MARKDOWN",
                    "version_no": 1,
                    "comment_count": 0,
                    "author_id": actor_id or f"project:{source.project_id}",
                    "author_user_id": user_id,
                    **payload,
                }
            )
        else:
            await repo.update(
                existing,
                {
                    **payload,
                    "version_no": (existing.version_no or 1) + 1,
                },
            )
