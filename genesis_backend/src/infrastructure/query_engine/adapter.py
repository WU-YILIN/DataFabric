"""
Module 4 — 查询引擎适配器（抽象层）
通过抽象基类 QueryEngineAdapter 隔离具体查询引擎的实现细节，
使 ViewCompiler 可以无缝切换底层引擎（SQLite → Presto/StarRocks）。

本地开发使用 SQLiteAdapter，生产环境替换为 StarRocksAdapter 或 PrestoAdapter 即可，
无需修改 ViewCompiler 的任何代码（开闭原则）。
"""

import sqlite3
from abc import ABC, abstractmethod

from sqlalchemy import create_engine, text

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class QueryEngineAdapter(ABC):
    """抽象查询引擎适配器接口。"""

    @abstractmethod
    def execute_ddl(self, sql: str) -> None:
        """执行 CREATE OR REPLACE VIEW 等 DDL 语句。"""
        ...

    @abstractmethod
    def query(self, sql: str) -> list[dict]:
        """执行 SELECT 查询并以列表字典形式返回结果（用于影子测试）。"""
        ...


class SQLiteAdapter(QueryEngineAdapter):
    """
    本地内存 SQLite 适配器（开发/演示专用）。

    视图定义存储在内存数据库中，服务重启后丢失。生产场景请使用
    StarRocksAdapter 或 PrestoAdapter。
    """

    _DB_PATH = "file:genesis_schema_on_read?mode=memory&cache=shared"

    def __init__(self) -> None:
        # 共享内存数据库在同一进程内所有连接均可访问
        self._conn = sqlite3.connect(self._DB_PATH, uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # 确保用于存放原始数据的基础表存在
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ods_raw_events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                server_time TEXT,
                project_key TEXT,
                remote_ip   TEXT,
                raw_payload TEXT
            )
        """)
        self._conn.commit()

    def execute_ddl(self, sql: str) -> None:
        """执行 DDL。SQLite 不支持 CREATE OR REPLACE VIEW，先 DROP 再 CREATE。"""
        try:
            # 从 SQL 中提取视图名称（如 "v_event_checkout"）并先删除旧版本
            upper_sql = sql.upper()
            if "CREATE" in upper_sql and "VIEW" in upper_sql:
                # 简单解析视图名：取 VIEW 关键字后的下一个 token
                tokens = sql.split()
                view_kw_idx = next((i for i, t in enumerate(tokens) if t.upper() == "VIEW"), None)
                if view_kw_idx is not None and view_kw_idx + 1 < len(tokens):
                    view_name = tokens[view_kw_idx + 1].split("(")[0].rstrip()
                    self._conn.execute(f"DROP VIEW IF EXISTS {view_name}")

            self._conn.execute(sql)
            self._conn.commit()
            logger.info("DDL executed on SQLite adapter", sql_preview=sql[:120])
        except sqlite3.Error as exc:
            logger.error("DDL execution failed", error=str(exc))
            raise

    def query(self, sql: str) -> list[dict]:
        cursor = self._conn.execute(sql)
        return [dict(row) for row in cursor.fetchall()]


# ── 单例（进程内共享同一个 SQLite 连接，避免视图丢失）─────────────────────────
class PostgresAdapter(QueryEngineAdapter):
    """
    PostgreSQL 适配器（生产环境模拟）。
    连接实际的 PostgreSQL 数据库（DataFabric 此时兼作 DW / ODS），
    自动创建表并在数据库中直接 CREATE OR REPLACE VIEW。
    """

    def __init__(self) -> None:
        # 使用同步引擎
        sync_url = settings.ASYNC_DATABASE_URL.replace("+asyncpg", "")
        if "+aiosqlite" in settings.ASYNC_DATABASE_URL:
            # 防御：如果错误使用了 sqlite 的连接串
            sync_url = settings.DATABASE_URL.replace("+aiosqlite", "") if settings.DATABASE_URL else "sqlite:///./genesis_local.db"
            
        self._engine = create_engine(sync_url)
        # 确保用于存放原始数据的基础表存在
        with self._engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ods_raw_events (
                    id          SERIAL PRIMARY KEY,
                    server_time TEXT,
                    project_key TEXT,
                    remote_ip   TEXT,
                    raw_payload JSONB
                )
            """))

    def execute_ddl(self, sql: str) -> None:
        """执行 CREATE OR REPLACE VIEW 等 DDL。"""
        try:
            with self._engine.begin() as conn:
                conn.execute(text(sql))
            logger.info("DDL executed on Postgres adapter", sql_preview=sql[:120])
        except Exception as exc:
            logger.error("DDL execution failed on Postgres", error=str(exc))
            raise

    def query(self, sql: str) -> list[dict]:
        with self._engine.connect() as conn:
            result = conn.execute(text(sql))
            return [dict(r._mapping) for r in result]

# ── 单例 ───────────────────────────────────────────────────────────────────────
_default_adapter: QueryEngineAdapter | None = None

def get_default_adapter() -> QueryEngineAdapter:
    """根据环境返回合适的配置适配器。"""
    global _default_adapter
    if _default_adapter is None:
        if settings.ENVIRONMENT.value == "production":
            _default_adapter = PostgresAdapter()
        else:
            _default_adapter = SQLiteAdapter()
    return _default_adapter
