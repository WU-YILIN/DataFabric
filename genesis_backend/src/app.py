import asyncio

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from src.utils.logger import setup_logging, get_logger
from src.config import settings
from src.api.middlewares.correlation import CorrelationIdMiddleware
from src.api.middlewares.timing import ProcessTimeMiddleware
from src.api.response import error_response
from src.api.v1.endpoints import auth
from src.domain.exceptions import AppError
from src.domain.auth.security import hash_password
from src.domain.pipeline.sync_scheduler import sync_pipeline_loop
from src.api.v1.endpoints import (
    governance,
    events,
    pipelines,
    audit,
    stats,
    overview,
    data_catalog,
    data_quality,
    scheduler,
    explore,
    infrastructure,
    settings as settings_router,
    monitoring,
    collaboration,
    analysis_planner,
    knowledge,
    cost,
    sandbox,
    integration_hub,
    access,
    policy,
    ingestion,
    release,
    reports,
    marketplace,
    incidents,
)
from src.infrastructure.database.models import Base
from src.infrastructure.database.models.tenant import Tenant, TenantStatus
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.project_repo import ProjectRepository
from src.infrastructure.database.repositories.user_repo import UserRepository
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.database.session import engine

setup_logging()
logger = get_logger(__name__)
pipeline_sync_stop_event: asyncio.Event | None = None
pipeline_sync_task: asyncio.Task | None = None

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middlewares
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(ProcessTimeMiddleware)

# Exception Handling
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.warning("Application error", error=exc.message, code=exc.code, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.message, exc.code),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(message, "HTTP_ERROR", exc.detail if not isinstance(exc.detail, str) else None),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response("Internal Server Error", "INTERNAL_ERROR"),
    )

# Routes
app.include_router(governance.router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(pipelines.router, prefix="/api/v1/pipelines", tags=["pipelines"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(overview.router, prefix="/api/v1/overview", tags=["overview"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(data_catalog.router, prefix="/api/v1/catalog", tags=["catalog"])
app.include_router(data_quality.router, prefix="/api/v1/data-quality", tags=["data-quality"])
app.include_router(scheduler.router, prefix="/api/v1/scheduler", tags=["scheduler"])
app.include_router(explore.router, prefix="/api/v1/explore", tags=["explore"])
app.include_router(infrastructure.router, prefix="/api/v1/infrastructure", tags=["infrastructure"])
app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(monitoring.router, prefix="/api/v1/monitoring", tags=["monitoring"])
app.include_router(collaboration.router, prefix="/api/v1/collaboration", tags=["collaboration"])
app.include_router(analysis_planner.router, prefix="/api/v1/analysis-planner", tags=["analysis-planner"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(cost.router, prefix="/api/v1/cost", tags=["cost"])
app.include_router(sandbox.router, prefix="/api/v1/sandbox", tags=["sandbox"])
app.include_router(integration_hub.router, prefix="/api/v1/integration-hub", tags=["integration-hub"])
app.include_router(access.router, prefix="/api/v1/access", tags=["access"])
app.include_router(policy.router, prefix="/api/v1/policy", tags=["policy"])
app.include_router(ingestion.router, prefix="/api/v1/ingestion", tags=["ingestion"])
app.include_router(release.router, prefix="/api/v1/release", tags=["release"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(marketplace.router, prefix="/api/v1/marketplace", tags=["marketplace"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])


async def _run_sqlite_compat_migrations() -> None:
    if not settings.ASYNC_DATABASE_URL.startswith("sqlite"):
        return

    async def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
        table_info = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing_columns = {row[1] for row in table_info.fetchall()}
        if column not in existing_columns:
            await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            logger.info("Applied sqlite compat migration", table=table, column=column)

    async with engine.begin() as conn:
        await _ensure_column(conn, "projects", "tenant_id", "tenant_id INTEGER")
        await _ensure_column(conn, "projects", "description", "description VARCHAR(1000)")
        await _ensure_column(conn, "projects", "tags", "tags JSON DEFAULT '[]'")
        await _ensure_column(conn, "projects", "default_domain", "default_domain VARCHAR(128)")
        await _ensure_column(conn, "tracking_events", "owner", "owner VARCHAR(255)")
        await _ensure_column(conn, "tracking_events", "tags", "tags JSON DEFAULT '[]'")
        await _ensure_column(
            conn,
            "tracking_events",
            "governance_status",
            "governance_status VARCHAR(32) DEFAULT 'NOT_CHECKED'",
        )
        await _ensure_column(conn, "audit_logs", "details", "details VARCHAR(4000)")
        await _ensure_column(conn, "governance_checks", "event_id", "event_id INTEGER")
        await _ensure_column(
            conn, "governance_checks", "model_name", "model_name VARCHAR(100) DEFAULT 'gpt-4o-mini'"
        )
        await _ensure_column(conn, "governance_checks", "request_payload", "request_payload JSON DEFAULT '{}'")
        await _ensure_column(conn, "governance_checks", "result_payload", "result_payload JSON DEFAULT '{}'")
        await _ensure_column(conn, "data_quality_rules", "asset_id", "asset_id INTEGER")
        await _ensure_column(conn, "data_quality_rules", "alert_channels", "alert_channels JSON DEFAULT '[]'")
        await _ensure_column(conn, "user_tenant_roles", "created_at", "created_at DATETIME")
        await _ensure_column(conn, "user_tenant_roles", "updated_at", "updated_at DATETIME")
        await _ensure_column(conn, "user_project_roles", "created_at", "created_at DATETIME")
        await _ensure_column(conn, "user_project_roles", "updated_at", "updated_at DATETIME")
        await _ensure_column(conn, "alerts", "claimed_by", "claimed_by VARCHAR(255)")
        await _ensure_column(conn, "alerts", "claimed_at", "claimed_at DATETIME")
        await _ensure_column(conn, "alerts", "last_note", "last_note VARCHAR(1000)")


async def _ensure_demo_tenant(session) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.slug == "demo"))
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant
    tenant_repo = BaseRepository(Tenant, session)
    return await tenant_repo.create(
        {
            "name": "Demo Tenant",
            "slug": "demo",
            "status": TenantStatus.ACTIVE,
        }
    )


async def _ensure_demo_project(session, tenant_id: int) -> Project:
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_name("demo_project")
    if not project:
        return await project_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "demo_project",
                "api_key": "demo-key-001",
                "tech_stack": {"mode": "demo"},
            }
        )
    if project.tenant_id != tenant_id:
        project = await project_repo.update(project, {"tenant_id": tenant_id})
    return project


async def _ensure_demo_user(session, tenant_id: int, project_id: int) -> None:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email("admin@demo.local")
    if not user:
        user = await user_repo.create(
            {
                "email": "admin@demo.local",
                "name": "Demo Admin",
                "auth_provider": "local",
                "password_hash": hash_password("demo123456"),
                "is_active": True,
            }
        )
    elif not user.password_hash:
        await user_repo.update(user, {"password_hash": hash_password("demo123456")})

    tenant_role_result = await session.execute(
        select(UserTenantRole).where(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
        )
    )
    tenant_role = tenant_role_result.scalar_one_or_none()
    if not tenant_role:
        tenant_role_repo = BaseRepository(UserTenantRole, session)
        await tenant_role_repo.create(
            {
                "user_id": user.id,
                "tenant_id": tenant_id,
                "role": "ADMIN",
            }
        )

    project_role_result = await session.execute(
        select(UserProjectRole).where(
            UserProjectRole.user_id == user.id,
            UserProjectRole.project_id == project_id,
        )
    )
    project_role = project_role_result.scalar_one_or_none()
    if not project_role:
        project_role_repo = BaseRepository(UserProjectRole, session)
        await project_role_repo.create(
            {
                "user_id": user.id,
                "project_id": project_id,
                "role": "OWNER",
            }
        )

@app.on_event("startup")
async def startup_event():
    global pipeline_sync_stop_event, pipeline_sync_task
    logger.info("Starting up Genesis Backend", environment=settings.ENVIRONMENT)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_sqlite_compat_migrations()
    async with async_session_factory() as session:
        tenant = await _ensure_demo_tenant(session)
        project = await _ensure_demo_project(session, tenant.id)
        await _ensure_demo_user(session, tenant.id, project.id)
        await session.commit()
    if settings.PIPELINE_AUTO_SYNC_ENABLED:
        pipeline_sync_stop_event = asyncio.Event()
        pipeline_sync_task = asyncio.create_task(sync_pipeline_loop(pipeline_sync_stop_event))
        logger.info("Pipeline auto-sync enabled")


@app.on_event("shutdown")
async def shutdown_event():
    global pipeline_sync_stop_event, pipeline_sync_task
    if pipeline_sync_stop_event is not None:
        pipeline_sync_stop_event.set()
    if pipeline_sync_task is not None:
        await pipeline_sync_task

@app.get("/health")
async def health_check():
    # In a real app, you'd check DB, Kafka, Flink, etc.
    return {"code": "OK", "message": "healthy", "data": {"project": settings.PROJECT_NAME}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
