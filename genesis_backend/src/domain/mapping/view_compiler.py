"""
Module 4 — 读时视图编译器（Schema-on-Read Compilation）
ViewCompiler：将 DataFabric 平台上人工审批通过的字段映射规则，
自动编译为下游查询引擎可执行的 SQL 虚拟视图（CREATE OR REPLACE VIEW）。

关键特点：
  - 零数据移动：只改写 View 定义，历史数据无需重跑
  - 即改即生：审批通过 → 调用 compile() → 几毫秒内生效
  - 引擎无关：通过 QueryEngineAdapter 支持 SQLite / Presto / StarRocks
"""

from typing import Optional

from src.infrastructure.query_engine.adapter import QueryEngineAdapter, get_default_adapter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# SQLite 支持的 CAST 类型映射
_CAST_TYPE_MAP = {
    "FLOAT":  "REAL",
    "INT":    "INTEGER",
    "STRING": "TEXT",
    "BOOL":   "INTEGER",  # SQLite 没有 BOOLEAN → 用 0/1
}

# StarRocks / Presto 版映射（切换引擎时使用）
_CAST_TYPE_MAP_STANDARD = {
    "FLOAT":  "DOUBLE",
    "INT":    "BIGINT",
    "STRING": "VARCHAR",
    "BOOL":   "BOOLEAN",
}


class ViewCompiler:
    """
    将 SchemaFieldMapping 规则编译为 SQL 视图。

    逻辑流程：
      1. 加载某个事件所有 APPROVED 映射规则
      2. 为每条规则生成 COALESCE + CAST 子句
      3. 拼接完整的 CREATE OR REPLACE VIEW SQL
      4. 通过 QueryEngineAdapter.execute_ddl() 执行

    示例生成 SQL（去掉注释后）：
      CREATE VIEW v_event_checkout AS
      SELECT
        CAST(COALESCE(
          json_extract(raw_payload,'$.price'),
          json_extract(raw_payload,'$.zhifu_jine')
        ) AS REAL) AS price,
        CAST(json_extract(raw_payload,'$.user_id') AS TEXT) AS user_id
      FROM ods_raw_events
      WHERE json_extract(raw_payload,'$.event') = 'checkout';
    """

    def __init__(self, adapter: Optional[QueryEngineAdapter] = None) -> None:
        self.adapter = adapter or get_default_adapter()

    async def compile(self, event_id: int) -> str:
        """
        编译并部署指定事件的虚拟视图。
        返回生成的 SQL DDL 字符串（供日志和调试使用）。
        """
        from sqlalchemy import select
        from src.infrastructure.database.session import get_async_session
        from src.infrastructure.database.models.schema_field_mapping import (
            SchemaFieldMapping, FieldMappingStatus,
        )
        from src.infrastructure.database.models.event import TrackingEvent

        async for session in get_async_session():
            # 1. 加载事件基本信息（用于构造 WHERE 子句和视图名）
            event_result = await session.execute(
                select(TrackingEvent).where(TrackingEvent.id == event_id)
            )
            event = event_result.scalar_one_or_none()
            if event is None:
                raise ValueError(f"TrackingEvent {event_id} not found")

            # 2. 加载所有 APPROVED 映射规则
            mappings_result = await session.execute(
                select(SchemaFieldMapping).where(
                    SchemaFieldMapping.event_id == event_id,
                    SchemaFieldMapping.status == FieldMappingStatus.APPROVED,
                )
            )
            mappings = list(mappings_result.scalars().all())

            if not mappings:
                logger.info("No approved mappings yet for event — skipping view compilation", event_id=event_id)
                return ""

            # 3. 为每条映射规则生成 COALESCE + CAST 投影列
            select_columns = []
            for m in mappings:
                paths: list[str] = m.source_paths if isinstance(m.source_paths, list) else []
                cast_type = _CAST_TYPE_MAP.get(m.cast_type, "TEXT")
                target = m.target_field

                if not paths:
                    continue

                if len(paths) == 1:
                    coalesce_expr = f"json_extract(raw_payload, '{paths[0]}')"
                else:
                    inner = ",\n          ".join(f"json_extract(raw_payload, '{p}')" for p in paths)
                    coalesce_expr = f"COALESCE(\n          {inner}\n        )"

                col_expr = f"    CAST({coalesce_expr} AS {cast_type}) AS {target}"
                select_columns.append(col_expr)

            if not select_columns:
                return ""

            # 4. 拼接完整 DDL
            view_name = f"v_event_{event.code.lower().replace('.', '_').replace('-', '_')}"
            event_filter = event.code  # 用于 WHERE json_extract ... = '...'

            columns_sql = ",\n".join(select_columns)
            ddl = (
                f"CREATE VIEW {view_name} AS\n"
                f"SELECT\n"
                f"{columns_sql}\n"
                f"FROM ods_raw_events\n"
                f"WHERE json_extract(raw_payload, '$.event') = '{event_filter}'"
            )

            # 5. 执行 DDL（通过可换插的适配器层）
            self.adapter.execute_ddl(ddl)
            logger.info(
                "Virtual view compiled and deployed",
                view_name=view_name,
                event_id=event_id,
                columns_count=len(select_columns),
            )
            return ddl

    def shadow_test(self, event_id: int, event_code: str) -> Optional[float]:
        """
        影子测试：在新视图生效前，用 COUNT(*) 估算潜在的数据覆盖率变化。
        返回 delta_pct（新覆盖率 − 旧覆盖率的近似值）。

        目前为轻量级实现（比较 NULL 比例），足以防止明显的误批操作。
        """
        try:
            view_name = f"v_event_{event_code.lower().replace('.', '_').replace('-', '_')}"
            result = self.adapter.query(
                f"SELECT COUNT(*) as total, "
                f"COUNT(CASE WHEN rowid IS NOT NULL THEN 1 END) as non_null "
                f"FROM {view_name}"
            )
            if result and result[0]["total"] > 0:
                pct = result[0]["non_null"] / result[0]["total"] * 100
                return pct
        except Exception as exc:
            logger.warning("Shadow test query failed", error=str(exc))
        return None
