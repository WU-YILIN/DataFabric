"""
Module 3+5 — 字段映射人工审批 REST API + 数据质量看板

Endpoints:
  GET    /schema-mapping/proposals           查看待审批 AI 建议列表
  GET    /schema-mapping/proposals/{id}      AI 建议详情 + 影子测试结果
  POST   /schema-mapping/proposals/{id}/approve  审批通过 → 自动触发视图编译
  POST   /schema-mapping/proposals/{id}/reject   拒绝（含原因）
  POST   /schema-mapping/scan                手动触发字段扫描任务
  GET    /schema-mapping/approved            所有生效中的映射规则
  DELETE /schema-mapping/approved/{id}       撤销一条已审批的映射规则
  GET    /schema-mapping/quality             质量看板（覆盖率 / 异常率 / Top 未知字段）
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import (
    RequestContext,
    TENANT_ELEVATED_ROLES,
    get_request_context,
)
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.ingestion_event_log import IngestionEventLog
from src.infrastructure.database.models.schema_field_mapping import (
    FieldCastType,
    FieldMappingStatus,
    SchemaFieldMapping,
)
from src.infrastructure.database.session import get_async_session
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# ── 权限角色集 ────────────────────────────────────────────────────────────────
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR"}

# ── Pydantic 请求模型 ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    event_id: int = Field(..., gt=0, description="要扫描的 TrackingEvent ID")
    limit: int = Field(default=500, ge=1, le=5000, description="扫描最近 N 条事件日志")


class ApproveRequest(BaseModel):
    cast_type: Optional[str] = Field(
        default=None,
        description="覆盖推断的类型转换（FLOAT/INT/STRING/BOOL），留空则保留 AI 建议",
    )
    source_paths: Optional[list[str]] = Field(
        default=None,
        description="覆盖推断的 JSONPath 路径列表，留空则保留原路径",
    )
    note: Optional[str] = Field(default=None, max_length=500)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ManualMappingRequest(BaseModel):
    event_id: int = Field(..., gt=0)
    target_field: str = Field(..., min_length=1, max_length=128)
    source_paths: list[str] = Field(..., min_items=1)
    cast_type: str = Field(default=FieldCastType.STRING)
    note: Optional[str] = Field(default=None, max_length=500)


# ── 内部辅助函数 ───────────────────────────────────────────────────────────────

def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _mapping_to_dict(m: SchemaFieldMapping) -> dict[str, Any]:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "event_id": m.event_id,
        "target_field": m.target_field,
        "source_paths": m.source_paths,
        "cast_type": m.cast_type,
        "status": m.status,
        "confidence_score": m.confidence_score,
        "proposed_by": m.proposed_by,
        "approved_by": m.approved_by,
        "ai_reasoning": m.ai_reasoning,
        "shadow_delta_pct": m.shadow_delta_pct,
        "field_frequency": m.field_frequency,
        "note": m.note,
        "created_at": _to_iso(m.created_at),
        "updated_at": _to_iso(m.updated_at),
    }


def _require_write_role(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES or tenant_role in TENANT_ELEVATED_ROLES:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要写入权限")


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="此接口需要用户身份认证")


async def _get_mapping_or_404(
    mapping_id: int,
    project_id: int,
    db: AsyncSession,
) -> SchemaFieldMapping:
    result = await db.execute(
        select(SchemaFieldMapping).where(
            SchemaFieldMapping.id == mapping_id,
            SchemaFieldMapping.project_id == project_id,
        )
    )
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="映射条目不存在")
    return m


# ── 查看待审批 AI 建议列表 ─────────────────────────────────────────────────────

@router.get("/proposals")
async def list_proposals(
    event_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)

    query = select(SchemaFieldMapping).where(
        SchemaFieldMapping.project_id == context.project.id
    )
    if event_id is not None:
        query = query.where(SchemaFieldMapping.event_id == event_id)
    if status_filter:
        query = query.where(SchemaFieldMapping.status == status_filter.upper())
    else:
        query = query.where(SchemaFieldMapping.status == FieldMappingStatus.PENDING)

    query = query.order_by(
        SchemaFieldMapping.field_frequency.desc(),
        SchemaFieldMapping.created_at.desc(),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    items_result = await db.execute(query.offset(offset).limit(limit))
    items = list(items_result.scalars().all())

    return success_response({
        "items": [_mapping_to_dict(m) for m in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ── 建议详情 ───────────────────────────────────────────────────────────────────

@router.get("/proposals/{mapping_id}")
async def get_proposal_detail(
    mapping_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    m = await _get_mapping_or_404(mapping_id, context.project.id, db)

    # 影子测试：预估该字段的覆盖率
    shadow_result = None
    try:
        from src.domain.mapping.view_compiler import ViewCompiler
        event_result = await db.execute(select(TrackingEvent).where(TrackingEvent.id == m.event_id))
        event = event_result.scalar_one_or_none()
        if event:
            compiler = ViewCompiler()
            shadow_result = compiler.shadow_test(m.event_id, event.code)
    except Exception as exc:
        logger.warning("Shadow test failed in detail endpoint", error=str(exc))

    data = _mapping_to_dict(m)
    data["shadow_coverage_pct"] = shadow_result
    return success_response(data)


# ── 审批通过映射规则 ───────────────────────────────────────────────────────────

@router.post("/proposals/{mapping_id}/approve")
async def approve_proposal(
    mapping_id: int,
    body: ApproveRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    _require_write_role(context)

    m = await _get_mapping_or_404(mapping_id, context.project.id, db)

    if m.status == FieldMappingStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该条目已经处于 APPROVED 状态")

    # 验证 cast_type 合法性
    allowed_cast = {FieldCastType.FLOAT, FieldCastType.INT, FieldCastType.STRING, FieldCastType.BOOL}
    if body.cast_type and body.cast_type.upper() not in allowed_cast:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的 cast_type: {body.cast_type}")

    actor = context.user.email if context.user else "unknown"

    # 应用覆盖更新（若请求中提供则覆盖 AI 建议）
    if body.cast_type:
        m.cast_type = body.cast_type.upper()
    if body.source_paths:
        m.source_paths = body.source_paths
    if body.note:
        m.note = body.note

    m.status = FieldMappingStatus.APPROVED
    m.approved_by = actor
    await db.commit()
    await db.refresh(m)

    # ── 关键：审批通过后立即重编译虚拟视图 ──────────────────────────────────────
    compiled_ddl: str = ""
    try:
        from src.domain.mapping.view_compiler import ViewCompiler
        compiler = ViewCompiler()
        compiled_ddl = await compiler.compile(m.event_id)
    except Exception as exc:
        logger.error("View compilation failed after approval", error=str(exc))
        # 非致命错误：映射已写入 DB，下次可手动触发重编译

    return success_response(
        {
            "mapping": _mapping_to_dict(m),
            "view_compiled": bool(compiled_ddl),
            "compiled_ddl_preview": compiled_ddl[:500] if compiled_ddl else None,
        },
        message="映射规则已审批通过，虚拟视图已重新编译",
        code="MAPPING_APPROVED",
    )


# ── 拒绝映射规则 ───────────────────────────────────────────────────────────────

@router.post("/proposals/{mapping_id}/reject")
async def reject_proposal(
    mapping_id: int,
    body: RejectRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    _require_write_role(context)

    m = await _get_mapping_or_404(mapping_id, context.project.id, db)
    if m.status == FieldMappingStatus.REJECTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该条目已经处于 REJECTED 状态")

    m.status = FieldMappingStatus.REJECTED
    m.note = body.reason
    await db.commit()
    await db.refresh(m)

    return success_response(
        {"mapping": _mapping_to_dict(m)},
        message="映射规则已拒绝",
        code="MAPPING_REJECTED",
    )


# ── 手动触发字段扫描任务 ───────────────────────────────────────────────────────

@router.post("/scan")
async def trigger_scan(
    body: ScanRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    _require_write_role(context)

    # 验证 event 属于当前项目
    event_result = await db.execute(
        select(TrackingEvent).where(
            TrackingEvent.id == body.event_id,
            TrackingEvent.project_id == context.project.id,
        )
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event 不存在或不属于当前项目")

    # 异步触发 Celery 扫描任务
    try:
        from src.worker.tasks.field_discovery import scan_raw_fields
        task = scan_raw_fields.delay(project_id=context.project.id, event_id=body.event_id)
        task_id = task.id
    except Exception as exc:
        # Celery 未就绪时（本地 in-memory broker），同步运行
        logger.warning("Celery unavailable, running scan synchronously", error=str(exc))
        from src.worker.tasks.field_discovery import _scan_async
        result = await _scan_async(project_id=context.project.id, event_id=body.event_id)
        return success_response({"sync_result": result}, message="扫描已同步完成", code="SCAN_COMPLETE_SYNC")

    return success_response(
        {"task_id": task_id, "event_id": body.event_id},
        message="字段发现扫描任务已提交到后台队列",
        code="SCAN_TRIGGERED",
    )


# ── 查看所有生效中（APPROVED）的映射规则 ──────────────────────────────────────

@router.get("/approved")
async def list_approved_mappings(
    event_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    query = select(SchemaFieldMapping).where(
        SchemaFieldMapping.project_id == context.project.id,
        SchemaFieldMapping.status == FieldMappingStatus.APPROVED,
    )
    if event_id is not None:
        query = query.where(SchemaFieldMapping.event_id == event_id)
    query = query.order_by(SchemaFieldMapping.event_id, SchemaFieldMapping.target_field)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    items_result = await db.execute(query.offset(offset).limit(limit))
    items = list(items_result.scalars().all())

    return success_response({
        "items": [_mapping_to_dict(m) for m in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ── 撤销已审批的映射规则 ───────────────────────────────────────────────────────

@router.delete("/approved/{mapping_id}")
async def revoke_mapping(
    mapping_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    _require_write_role(context)

    m = await _get_mapping_or_404(mapping_id, context.project.id, db)
    if m.status != FieldMappingStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有 APPROVED 状态的规则才能被撤销")

    m.status = FieldMappingStatus.REJECTED
    m.note = (m.note or "") + " [撤销]"
    await db.commit()

    # 重编译视图（移除该字段）
    try:
        from src.domain.mapping.view_compiler import ViewCompiler
        await ViewCompiler().compile(m.event_id)
    except Exception as exc:
        logger.warning("View recompilation after revoke failed (non-fatal)", error=str(exc))

    return success_response({"id": mapping_id}, message="映射规则已撤销", code="MAPPING_REVOKED")


# ── Module 5: 数据质量看板 ─────────────────────────────────────────────────────

@router.get("/quality")
async def get_quality_dashboard(
    event_id: Optional[int] = Query(default=None, description="只看指定事件的质量指标"),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    project_id = context.project.id

    # 查询所有该项目的映射规则
    base_query = select(SchemaFieldMapping).where(SchemaFieldMapping.project_id == project_id)
    if event_id is not None:
        base_query = base_query.where(SchemaFieldMapping.event_id == event_id)

    mappings_result = await db.execute(base_query)
    all_mappings = list(mappings_result.scalars().all())

    total = len(all_mappings)
    approved = [m for m in all_mappings if m.status == FieldMappingStatus.APPROVED]
    pending = [m for m in all_mappings if m.status == FieldMappingStatus.PENDING]
    rejected = [m for m in all_mappings if m.status == FieldMappingStatus.REJECTED]

    # 按字段频率排序，取 Top 5 未审批字段（辅助分析师优先化工作）
    top_unknown = sorted(pending, key=lambda m: m.field_frequency, reverse=True)[:5]

    # 高置信度待审批数（>= 0.90，可借助自动审批 Bot 处理）
    high_confidence_pending = [m for m in pending if m.confidence_score >= 0.90]

    # 覆盖率 = 已审批 / 有效条目（approved + pending）
    effective_total = len(approved) + len(pending)
    coverage_pct = (len(approved) / effective_total * 100) if effective_total > 0 else 0.0

    # 平均 AI 置信度
    avg_confidence = (
        sum(m.confidence_score for m in all_mappings) / total if total > 0 else 0.0
    )

    return success_response({
        "summary": {
            "total_mappings": total,
            "approved": len(approved),
            "pending": len(pending),
            "rejected": len(rejected),
            "coverage_pct": round(coverage_pct, 1),
            "avg_ai_confidence": round(avg_confidence, 3),
            "high_confidence_pending": len(high_confidence_pending),
        },
        "top_unknown_fields": [
            {
                "id": m.id,
                "target_field": m.target_field,
                "source_paths": m.source_paths,
                "frequency": m.field_frequency,
                "confidence_score": m.confidence_score,
                "ai_reasoning": m.ai_reasoning,
            }
            for m in top_unknown
        ],
        "high_confidence_proposals": [
            _mapping_to_dict(m) for m in high_confidence_pending[:10]
        ],
    })


# ── 手动创建映射规则（人工指定，不需要 AI Discovery）────────────────────────────

@router.post("/manual")
async def create_manual_mapping(
    body: ManualMappingRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
) -> Any:
    _require_user_context(context)
    _require_write_role(context)

    # 验证 cast_type
    allowed_cast = {FieldCastType.FLOAT, FieldCastType.INT, FieldCastType.STRING, FieldCastType.BOOL}
    if body.cast_type.upper() not in allowed_cast:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的 cast_type: {body.cast_type}")

    # 验证 event 属于当前项目
    event_result = await db.execute(
        select(TrackingEvent).where(
            TrackingEvent.id == body.event_id,
            TrackingEvent.project_id == context.project.id,
        )
    )
    if event_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event 不存在或不属于当前项目")

    actor = context.user.email if context.user else "unknown"
    new_mapping = SchemaFieldMapping(
        project_id=context.project.id,
        event_id=body.event_id,
        target_field=body.target_field.strip(),
        source_paths=body.source_paths,
        cast_type=body.cast_type.upper(),
        status=FieldMappingStatus.APPROVED,  # 人工创建直接 APPROVED
        confidence_score=1.0,
        proposed_by="human",
        approved_by=actor,
        note=body.note,
        field_frequency=0,
    )
    db.add(new_mapping)
    await db.commit()
    await db.refresh(new_mapping)

    # 立即重编译视图
    try:
        from src.domain.mapping.view_compiler import ViewCompiler
        await ViewCompiler().compile(body.event_id)
    except Exception as exc:
        logger.warning("View compilation failed after manual create", error=str(exc))

    return success_response(
        {"mapping": _mapping_to_dict(new_mapping)},
        message="人工映射规则已创建并生效",
        code="MAPPING_MANUAL_CREATED",
    )
