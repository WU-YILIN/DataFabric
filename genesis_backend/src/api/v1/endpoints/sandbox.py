import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.sandbox_experiment import SandboxExperiment
from src.infrastructure.database.models.sandbox_experiment_run import SandboxExperimentRun
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ALLOWED_EXPERIMENT_TYPES = {
    "EVENT_EXPERIMENT",
    "DQ_RULE_EXPERIMENT",
    "PIPELINE_EXPERIMENT",
    "QUERY_EXPERIMENT",
}
ALLOWED_STATUS = {"DRAFT", "RUNNING", "COMPLETED", "PROMOTED", "CANCELLED"}
ALLOWED_SOURCE_TYPES = {"TRACKING_EVENT", "DATA_QUALITY_RULE", "PIPELINE", "QUERY_TEMPLATE"}
EXPERIMENT_SOURCE_COMPATIBILITY = {
    "EVENT_EXPERIMENT": {"TRACKING_EVENT"},
    "DQ_RULE_EXPERIMENT": {"DATA_QUALITY_RULE"},
    "PIPELINE_EXPERIMENT": {"PIPELINE"},
    "QUERY_EXPERIMENT": {"QUERY_TEMPLATE"},
}
SOURCE_ROUTE_MAP = {
    "TRACKING_EVENT": "/events",
    "DATA_QUALITY_RULE": "/data-quality",
    "PIPELINE": "/pipelines",
    "QUERY_TEMPLATE": "/explore",
}
PROMOTION_ACTION_MAP = {
    "TRACKING_EVENT": "SANDBOX_EXPERIMENT_PROMOTE_EVENT",
    "DATA_QUALITY_RULE": "SANDBOX_EXPERIMENT_PROMOTE_DQ_RULE",
    "PIPELINE": "SANDBOX_EXPERIMENT_PROMOTE_PIPELINE",
    "QUERY_TEMPLATE": "SANDBOX_EXPERIMENT_PROMOTE_QUERY",
}


class SandboxExperimentCreateRequest(BaseModel):
    experiment_type: str = Field(..., min_length=3, max_length=64)
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    source_type: str = Field(..., min_length=2, max_length=64)
    source_id: str = Field(..., min_length=1, max_length=128)
    sandbox_source_type: str | None = Field(default=None, max_length=64)
    sandbox_source_id: str | None = Field(default=None, max_length=128)
    config_payload: dict[str, Any] = Field(default_factory=dict)


class SandboxExperimentRunRequest(BaseModel):
    sample_size: int = Field(default=1000, ge=100, le=1000000)
    traffic_ratio: float = Field(default=0.1, ge=0.01, le=1.0)
    candidate_payloads: list[dict[str, Any]] = Field(default_factory=list)
    run_context: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=1000)


class SandboxExperimentPromoteRequest(BaseModel):
    candidate_key: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=1000)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _normalize_token(value: str, *, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} cannot be empty")
    return normalized


def _normalize_experiment_type(value: str) -> str:
    normalized = _normalize_token(value, field_name="experiment_type")
    if normalized not in ALLOWED_EXPERIMENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported experiment_type: {value}")
    return normalized


def _normalize_source_type(value: str) -> str:
    normalized = _normalize_token(value, field_name="source_type")
    if normalized not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported source_type: {value}")
    return normalized


def _normalize_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_token(value, field_name="status")
    if normalized not in ALLOWED_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {value}")
    return normalized


def _normalize_candidate_key(raw_value: str, fallback: str) -> str:
    value = re.sub(r"[^a-z0-9_\-]+", "_", raw_value.strip().lower()).strip("_")
    return value or fallback


def _stable_seed(value: str) -> int:
    result = 0
    for char in value:
        result = (result * 131 + ord(char)) % 999983
    return result


def _stable_random(seed: int, salt: int) -> float:
    raw = math.sin(seed * 12.9898 + salt * 78.233) * 43758.5453
    return raw - math.floor(raw)


def _bump_patch_version(version: str) -> str:
    try:
        major, minor, patch = [int(item) for item in version.split(".")]
    except Exception:
        major, minor, patch = 1, 0, 0
    return f"{major}.{minor}.{patch + 1}"


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sandbox API requires bearer user context")


def _experiment_to_row(experiment: SandboxExperiment) -> dict[str, Any]:
    return {
        "id": experiment.id,
        "project_id": experiment.project_id,
        "tenant_id": experiment.tenant_id,
        "experiment_type": experiment.experiment_type,
        "title": experiment.title,
        "description": experiment.description,
        "status": experiment.status,
        "source_type": experiment.source_type,
        "source_id": experiment.source_id,
        "sandbox_source_type": experiment.sandbox_source_type,
        "sandbox_source_id": experiment.sandbox_source_id,
        "source_route": SOURCE_ROUTE_MAP.get(experiment.source_type, "/"),
        "created_by": parse_actor(experiment.created_by),
        "created_by_id": experiment.created_by,
        "updated_by": parse_actor(experiment.updated_by),
        "updated_by_id": experiment.updated_by,
        "config_payload": experiment.config_payload or {},
        "baseline_payload": experiment.baseline_payload or {},
        "best_candidate_payload": experiment.best_candidate_payload or {},
        "conclusion": experiment.conclusion or {},
        "promote_target_type": experiment.promote_target_type,
        "promote_target_id": experiment.promote_target_id,
        "promoted_at": _to_iso(experiment.promoted_at),
        "created_at": _to_iso(experiment.created_at),
        "updated_at": _to_iso(experiment.updated_at),
    }


def _run_to_row(run: SandboxExperimentRun) -> dict[str, Any]:
    recommendation = run.recommendation_payload if isinstance(run.recommendation_payload, dict) else {}
    return {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "project_id": run.project_id,
        "run_no": run.run_no,
        "status": run.status,
        "triggered_by": parse_actor(run.triggered_by),
        "triggered_by_id": run.triggered_by,
        "started_at": _to_iso(run.started_at),
        "finished_at": _to_iso(run.finished_at),
        "duration_ms": run.duration_ms,
        "run_context": run.run_context or {},
        "report_payload": run.report_payload or {},
        "recommendation_payload": recommendation,
        "created_at": _to_iso(run.created_at),
    }


def _summarize_audit_details(details: dict[str, Any]) -> str:
    for key in ("summary", "reason", "message", "note", "decision"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if "best_candidate_key" in details:
        return f"best_candidate={details.get('best_candidate_key')}"
    return ""

async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    experiment: SandboxExperiment,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "SANDBOX_EXPERIMENT",
            "entity_id": str(experiment.id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _resolve_baseline_payload(
    db: AsyncSession,
    *,
    project_id: int,
    source_type: str,
    source_id: str,
) -> dict[str, Any]:
    normalized_source_type = source_type.upper()
    if normalized_source_type == "TRACKING_EVENT":
        if not source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id must be numeric for TRACKING_EVENT")
        result = await db.execute(
            select(TrackingEvent).where(TrackingEvent.id == int(source_id), TrackingEvent.project_id == project_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TrackingEvent source not found")
        return {
            "event": {
                "id": event.id,
                "code": event.code,
                "name": event.name,
                "description": event.description,
                "domain": event.domain,
                "properties": event.properties or {},
                "status": event.status,
                "governance_status": event.governance_status,
                "version": event.version,
            }
        }

    if normalized_source_type == "DATA_QUALITY_RULE":
        if not source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id must be numeric for DATA_QUALITY_RULE")
        result = await db.execute(
            select(DataQualityRule).where(DataQualityRule.id == int(source_id), DataQualityRule.project_id == project_id)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DataQualityRule source not found")
        execution_result = await db.execute(
            select(DataQualityExecutionLog)
            .where(DataQualityExecutionLog.rule_id == rule.id, DataQualityExecutionLog.project_id == project_id)
            .order_by(DataQualityExecutionLog.executed_at.desc())
            .limit(30)
        )
        executions = list(execution_result.scalars().all())
        checked_count = sum(max(0, item.checked_count) for item in executions)
        failed_count = sum(max(0, item.failed_count) for item in executions)
        observed_failure_rate = (failed_count / checked_count) if checked_count > 0 else 0.0
        return {
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "rule_type": rule.rule_type,
                "target_field": rule.target_field,
                "operator": rule.operator,
                "threshold": rule.threshold or {},
                "severity": rule.severity,
                "status": rule.status,
                "version": rule.version,
            },
            "history": {
                "run_count": len(executions),
                "checked_count": checked_count,
                "failed_count": failed_count,
                "observed_failure_rate": round(observed_failure_rate, 6),
            },
        }

    if normalized_source_type == "PIPELINE":
        if not source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id must be numeric for PIPELINE")
        result = await db.execute(select(Pipeline).where(Pipeline.id == int(source_id), Pipeline.project_id == project_id))
        pipeline = result.scalar_one_or_none()
        if not pipeline:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pipeline source not found")
        return {
            "pipeline": {
                "id": pipeline.id,
                "event_code": pipeline.event_code,
                "topic_name": pipeline.topic_name,
                "flink_job_name": pipeline.flink_job_name,
                "status": pipeline.status,
                "config": pipeline.config or {},
                "retry_count": pipeline.retry_count,
            }
        }

    if normalized_source_type == "QUERY_TEMPLATE":
        return {"query_template": {"source_id": source_id, "sql": "", "description": ""}}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported source_type: {source_type}")


def _normalize_candidate_payloads(request_payloads: list[dict[str, Any]], experiment: SandboxExperiment) -> list[dict[str, Any]]:
    raw_candidates = request_payloads if request_payloads else [{"config": experiment.config_payload or {}}]
    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for index, raw_item in enumerate(raw_candidates, start=1):
        config = raw_item.get("config") if isinstance(raw_item.get("config"), dict) else {
            k: v for k, v in raw_item.items() if k not in {"key", "title", "notes"}
        }
        requested_key = str(raw_item.get("key") or f"candidate_{index}")
        key = _normalize_candidate_key(requested_key, fallback=f"candidate_{index}")
        if key in seen_keys:
            key = f"{key}_{index}"
        seen_keys.add(key)
        normalized.append(
            {
                "key": key,
                "title": str(raw_item.get("title") or f"Candidate {index}")[:120],
                "config": config if isinstance(config, dict) else {},
                "notes": raw_item.get("notes") if isinstance(raw_item.get("notes"), str) else None,
            }
        )

    return normalized


def _simulate_for_type(
    *,
    experiment_type: str,
    baseline_payload: dict[str, Any],
    run_no: int,
    sample_size: int,
    traffic_ratio: float,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    seed = _stable_seed(f"{experiment_type}|{run_no}|{sample_size}|{traffic_ratio}")
    if experiment_type == "EVENT_EXPERIMENT":
        base = {
            "hit_rate": 0.78,
            "field_completeness": 0.83,
            "naming_score": 0.81,
            "validation_pass_rate": 0.79,
        }
    elif experiment_type == "DQ_RULE_EXPERIMENT":
        observed = baseline_payload.get("history", {}).get("observed_failure_rate", 0.06)
        base = {
            "alert_rate": _clamp(float(observed) * 1.08, 0.005, 0.45),
            "false_positive_rate": 0.16,
            "false_negative_rate": 0.12,
            "pass_rate": _clamp(1.0 - float(observed) * 1.08, 0.2, 0.995),
        }
    elif experiment_type == "PIPELINE_EXPERIMENT":
        config = baseline_payload.get("pipeline", {}).get("config", {})
        partitions = int(config.get("partitions", 6) or 6)
        base = {
            "throughput_rps": 260 + partitions * 70 * traffic_ratio,
            "latency_ms": max(120.0, 430 - partitions * 10),
            "error_rate": 0.022,
            "resource_cost_index": 2.5 + partitions * 0.45,
        }
    else:
        base = {
            "execution_ms": 720.0,
            "scanned_rows": max(500.0, sample_size * 3.4),
            "success_rate": 0.91,
            "result_stability": 0.92,
        }

    def _score(metrics: dict[str, float]) -> float:
        if experiment_type == "EVENT_EXPERIMENT":
            return (
                metrics["hit_rate"] * 100 * 0.35
                + metrics["field_completeness"] * 100 * 0.30
                + metrics["naming_score"] * 100 * 0.20
                + metrics["validation_pass_rate"] * 100 * 0.15
            )
        if experiment_type == "DQ_RULE_EXPERIMENT":
            return (
                (1 - metrics["false_positive_rate"]) * 100 * 0.35
                + (1 - metrics["false_negative_rate"]) * 100 * 0.35
                + (1 - metrics["alert_rate"]) * 100 * 0.15
                + metrics["pass_rate"] * 100 * 0.15
            )
        if experiment_type == "PIPELINE_EXPERIMENT":
            return (
                _clamp(metrics["throughput_rps"] / 1200, 0, 1) * 100 * 0.40
                + (1 - _clamp(metrics["latency_ms"] / 1000, 0, 1)) * 100 * 0.25
                + (1 - metrics["error_rate"]) * 100 * 0.25
                + (1 - _clamp(metrics["resource_cost_index"] / 40, 0, 1)) * 100 * 0.10
            )
        return (
            (1 - _clamp(metrics["execution_ms"] / 3000, 0, 1)) * 100 * 0.45
            + metrics["success_rate"] * 100 * 0.30
            + metrics["result_stability"] * 100 * 0.20
            + (1 - _clamp(metrics["scanned_rows"] / (sample_size * 12), 0, 1)) * 100 * 0.05
        )

    baseline = {**base, "score": round(_score(base), 4)}

    reports: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        cfg = candidate.get("config") if isinstance(candidate.get("config"), dict) else {}
        cseed = seed + index * 17 + _stable_seed(json.dumps(cfg, sort_keys=True, ensure_ascii=True))
        metrics = dict(base)

        if experiment_type == "EVENT_EXPERIMENT":
            metrics["hit_rate"] = _clamp(base["hit_rate"] + (_stable_random(cseed, 1) - 0.5) * 0.09, 0.5, 0.999)
            metrics["field_completeness"] = _clamp(base["field_completeness"] + (_stable_random(cseed, 2) - 0.5) * 0.08, 0.5, 0.999)
            metrics["naming_score"] = _clamp(base["naming_score"] + (_stable_random(cseed, 3) - 0.5) * 0.1, 0.5, 0.999)
            metrics["validation_pass_rate"] = _clamp(base["validation_pass_rate"] + (_stable_random(cseed, 4) - 0.5) * 0.1, 0.45, 0.999)
        elif experiment_type == "DQ_RULE_EXPERIMENT":
            strictness = _clamp((0.08 - float(cfg.get("threshold", {}).get("max_failure_rate", 0.05))) * 8, -0.35, 0.45)
            metrics["alert_rate"] = _clamp(base["alert_rate"] + strictness * 0.12 + (_stable_random(cseed, 1) - 0.5) * 0.08, 0.001, 0.95)
            metrics["false_positive_rate"] = _clamp(base["false_positive_rate"] + strictness * 0.2 + (_stable_random(cseed, 2) - 0.5) * 0.08, 0.001, 0.95)
            metrics["false_negative_rate"] = _clamp(base["false_negative_rate"] - strictness * 0.18 + (_stable_random(cseed, 3) - 0.5) * 0.08, 0.001, 0.95)
            metrics["pass_rate"] = _clamp(1.0 - metrics["alert_rate"], 0.01, 0.999)
        elif experiment_type == "PIPELINE_EXPERIMENT":
            pcfg = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
            factor = max(0.5, min(2.5, float(pcfg.get("parallelism", 6)) / 6))
            metrics["throughput_rps"] = max(10.0, base["throughput_rps"] * factor + (_stable_random(cseed, 1) - 0.5) * 80)
            metrics["latency_ms"] = max(20.0, base["latency_ms"] / factor + (_stable_random(cseed, 2) - 0.5) * 90)
            metrics["error_rate"] = _clamp(base["error_rate"] + (_stable_random(cseed, 3) - 0.5) * 0.03, 0.0005, 0.99)
            metrics["resource_cost_index"] = max(0.1, base["resource_cost_index"] * factor + (_stable_random(cseed, 4) - 0.5) * 3)
        else:
            sql = str(cfg.get("sql", "") or "")
            slen = max(30, len(sql))
            metrics["execution_ms"] = max(10.0, base["execution_ms"] * _clamp(slen / 200, 0.55, 2.1) + (_stable_random(cseed, 1) - 0.5) * 180)
            metrics["scanned_rows"] = max(50.0, base["scanned_rows"] * _clamp(slen / 180, 0.6, 2.4) + (_stable_random(cseed, 2) - 0.5) * sample_size * 0.4)
            metrics["success_rate"] = _clamp(base["success_rate"] + (_stable_random(cseed, 3) - 0.5) * 0.1, 0.4, 0.999)
            metrics["result_stability"] = _clamp(base["result_stability"] + (_stable_random(cseed, 4) - 0.5) * 0.09, 0.45, 0.999)

        metrics["score"] = round(_score(metrics), 4)
        reports.append(
            {
                "key": candidate["key"],
                "title": candidate["title"],
                "config": cfg,
                "notes": candidate.get("notes"),
                "metrics": {k: round(float(v), 6) if k != "score" else float(v) for k, v in metrics.items()},
                "delta_vs_baseline": {
                    key: round(float(metrics[key]) - float(base.get(key, 0.0)), 6)
                    for key in base.keys()
                } | {"score": round(float(metrics["score"]) - float(baseline["score"]), 4)},
            }
        )

    best = max(reports, key=lambda item: item["metrics"]["score"])
    best_score = float(best["metrics"]["score"])
    baseline_score = float(baseline["score"])
    decision = "PROMOTE_RECOMMENDED" if best_score >= baseline_score + 1.5 else "REVIEW_REQUIRED"
    recommendation = {
        "best_candidate_key": best["key"],
        "best_score": round(best_score, 4),
        "baseline_score": round(baseline_score, 4),
        "decision": decision,
        "reason": "Candidate outperforms baseline" if decision == "PROMOTE_RECOMMENDED" else "Improvement is marginal, review before promotion",
        "candidate_rank": [
            {"key": item["key"], "score": item["metrics"]["score"]}
            for item in sorted(reports, key=lambda row: row["metrics"]["score"], reverse=True)
        ],
    }
    return {"baseline": baseline, "candidate_reports": reports}, recommendation, best

async def _get_experiment_or_404(db: AsyncSession, *, project_id: int, experiment_id: int) -> SandboxExperiment:
    result = await db.execute(
        select(SandboxExperiment).where(
            SandboxExperiment.id == experiment_id,
            SandboxExperiment.project_id == project_id,
        )
    )
    experiment = result.scalar_one_or_none()
    if not experiment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")
    return experiment


async def _latest_experiment_run(db: AsyncSession, *, experiment_id: int) -> SandboxExperimentRun | None:
    result = await db.execute(
        select(SandboxExperimentRun)
        .where(SandboxExperimentRun.experiment_id == experiment_id)
        .order_by(SandboxExperimentRun.run_no.desc(), SandboxExperimentRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _extract_candidate_from_run(run: SandboxExperimentRun, candidate_key: str | None) -> dict[str, Any]:
    report_payload = run.report_payload if isinstance(run.report_payload, dict) else {}
    recommendation_payload = run.recommendation_payload if isinstance(run.recommendation_payload, dict) else {}
    reports = report_payload.get("candidate_reports")
    if not isinstance(reports, list) or not reports:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No candidate reports available for promotion")

    resolved_key = candidate_key or recommendation_payload.get("best_candidate_key")
    if resolved_key:
        for row in reports:
            if isinstance(row, dict) and str(row.get("key")) == str(resolved_key):
                return row
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"candidate_key not found in latest run: {resolved_key}")
    return reports[0] if isinstance(reports[0], dict) else {}


async def _apply_promotion_to_source(db: AsyncSession, *, experiment: SandboxExperiment, candidate: dict[str, Any]) -> dict[str, Any]:
    config = candidate.get("config") if isinstance(candidate.get("config"), dict) else {}

    if experiment.source_type == "TRACKING_EVENT":
        if not experiment.source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event source_id")
        result = await db.execute(
            select(TrackingEvent).where(TrackingEvent.id == int(experiment.source_id), TrackingEvent.project_id == experiment.project_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event source not found")
        patch = config.get("event_patch") if isinstance(config.get("event_patch"), dict) else config
        allowed_fields = {"name", "description", "properties", "domain", "owner", "tags", "status", "governance_status"}
        update_data = {key: value for key, value in patch.items() if key in allowed_fields}
        if "status" in update_data and isinstance(update_data["status"], str):
            update_data["status"] = update_data["status"].lower()
        if update_data:
            update_data["version"] = _bump_patch_version(event.version)
            await BaseRepository(TrackingEvent, db).update(event, update_data)
        return {"target_type": "TRACKING_EVENT", "target_id": str(event.id), "route": "/events"}

    if experiment.source_type == "DATA_QUALITY_RULE":
        if not experiment.source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid rule source_id")
        result = await db.execute(
            select(DataQualityRule).where(DataQualityRule.id == int(experiment.source_id), DataQualityRule.project_id == experiment.project_id)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DQ rule source not found")
        patch = config.get("rule_patch") if isinstance(config.get("rule_patch"), dict) else config
        allowed_fields = {"name", "rule_type", "target_field", "operator", "threshold", "alert_channels", "severity", "status", "description"}
        update_data = {key: value for key, value in patch.items() if key in allowed_fields}
        if update_data:
            update_data["version"] = _bump_patch_version(rule.version)
            await BaseRepository(DataQualityRule, db).update(rule, update_data)
        return {"target_type": "DATA_QUALITY_RULE", "target_id": str(rule.id), "route": "/data-quality"}

    if experiment.source_type == "PIPELINE":
        if not experiment.source_id.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pipeline source_id")
        result = await db.execute(
            select(Pipeline).where(Pipeline.id == int(experiment.source_id), Pipeline.project_id == experiment.project_id)
        )
        pipeline = result.scalar_one_or_none()
        if not pipeline:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline source not found")
        patch = config.get("pipeline_patch") if isinstance(config.get("pipeline_patch"), dict) else config
        allowed_fields = {"event_code", "topic_name", "flink_job_name", "status", "error_message", "retry_count"}
        update_data = {key: value for key, value in patch.items() if key in allowed_fields}
        patch_config = patch.get("config") if isinstance(patch.get("config"), dict) else {}
        if patch_config:
            current_config = pipeline.config if isinstance(pipeline.config, dict) else {}
            update_data["config"] = {**current_config, **patch_config}
        if update_data:
            await BaseRepository(Pipeline, db).update(pipeline, update_data)
        return {"target_type": "PIPELINE", "target_id": str(pipeline.id), "route": "/pipelines"}

    return {"target_type": "QUERY_TEMPLATE", "target_id": experiment.source_id, "route": "/explore"}


@router.get("/overview")
async def get_sandbox_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    experiments_result = await db.execute(
        select(SandboxExperiment)
        .where(SandboxExperiment.project_id == context.project.id)
        .order_by(SandboxExperiment.updated_at.desc(), SandboxExperiment.id.desc())
    )
    experiments = list(experiments_result.scalars().all())

    runs_result = await db.execute(
        select(SandboxExperimentRun)
        .where(SandboxExperimentRun.project_id == context.project.id)
        .order_by(SandboxExperimentRun.created_at.desc(), SandboxExperimentRun.id.desc())
        .limit(200)
    )
    runs = list(runs_result.scalars().all())
    latest_run_by_experiment: dict[int, SandboxExperimentRun] = {}
    for run in runs:
        if run.experiment_id not in latest_run_by_experiment:
            latest_run_by_experiment[run.experiment_id] = run

    now = datetime.now(timezone.utc)
    runs_7d = sum(
        1
        for run in runs
        if _as_utc(run.created_at) and _as_utc(run.created_at) >= now - timedelta(days=7)
    )

    status_counts: dict[str, int] = {key: 0 for key in sorted(ALLOWED_STATUS)}
    type_counts: dict[str, int] = {}
    for item in experiments:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        type_counts[item.experiment_type] = type_counts.get(item.experiment_type, 0) + 1

    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "SANDBOX_EXPERIMENT", build_project_audit_filter(context.project.id)))
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(20)
    )
    recent_activity = [
        {
            "id": row.id,
            "timestamp": _to_iso(row.timestamp),
            "actor": parse_actor(row.user_id),
            "action": row.action,
            "entity_id": row.entity_id,
            "summary": _summarize_audit_details(_safe_json_loads(row.details)),
        }
        for row in audit_result.scalars().all()
    ]

    return success_response(
        {
            "summary": {
                "total_experiments": len(experiments),
                "draft_count": status_counts.get("DRAFT", 0),
                "running_count": status_counts.get("RUNNING", 0),
                "completed_count": status_counts.get("COMPLETED", 0),
                "promoted_count": status_counts.get("PROMOTED", 0),
                "cancelled_count": status_counts.get("CANCELLED", 0),
                "runs_7d": runs_7d,
            },
            "status_counts": status_counts,
            "type_counts": type_counts,
            "recent_experiments": [
                {
                    **_experiment_to_row(item),
                    "latest_run": _run_to_row(latest_run_by_experiment[item.id]) if item.id in latest_run_by_experiment else None,
                }
                for item in experiments[:12]
            ],
            "pending_promotion": [
                _experiment_to_row(item)
                for item in experiments
                if item.status == "COMPLETED" and not item.promoted_at
            ][:10],
            "recent_activity": recent_activity,
        }
    )

@router.get("/options")
async def get_sandbox_options(
    experiment_type: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_experiment_type(experiment_type) if experiment_type else None
    source_types = sorted(EXPERIMENT_SOURCE_COMPATIBILITY[normalized_type]) if normalized_type else sorted(ALLOWED_SOURCE_TYPES)

    event_options: list[dict[str, Any]] = []
    dq_options: list[dict[str, Any]] = []
    pipeline_options: list[dict[str, Any]] = []
    query_options: list[dict[str, Any]] = []

    if "TRACKING_EVENT" in source_types:
        result = await db.execute(
            select(TrackingEvent)
            .where(TrackingEvent.project_id == context.project.id)
            .order_by(TrackingEvent.updated_at.desc(), TrackingEvent.id.desc())
            .limit(200)
        )
        event_options = [
            {
                "id": str(item.id),
                "label": f"{item.code} | {item.name}",
                "code": item.code,
                "name": item.name,
                "status": item.status,
                "governance_status": item.governance_status,
            }
            for item in result.scalars().all()
        ]

    if "DATA_QUALITY_RULE" in source_types:
        result = await db.execute(
            select(DataQualityRule)
            .where(DataQualityRule.project_id == context.project.id)
            .order_by(DataQualityRule.updated_at.desc(), DataQualityRule.id.desc())
            .limit(200)
        )
        dq_options = [
            {
                "id": str(item.id),
                "label": f"{item.name} | {item.rule_type}",
                "name": item.name,
                "rule_type": item.rule_type,
                "severity": item.severity,
                "status": item.status,
            }
            for item in result.scalars().all()
        ]

    if "PIPELINE" in source_types:
        result = await db.execute(
            select(Pipeline)
            .where(Pipeline.project_id == context.project.id)
            .order_by(Pipeline.updated_at.desc(), Pipeline.id.desc())
            .limit(200)
        )
        pipeline_options = [
            {
                "id": str(item.id),
                "label": f"{item.flink_job_name} | {item.topic_name}",
                "event_code": item.event_code,
                "topic_name": item.topic_name,
                "flink_job_name": item.flink_job_name,
                "status": item.status,
            }
            for item in result.scalars().all()
        ]

    if "QUERY_TEMPLATE" in source_types:
        result = await db.execute(
            select(SandboxExperiment.source_id, func.max(SandboxExperiment.updated_at))
            .where(
                SandboxExperiment.project_id == context.project.id,
                SandboxExperiment.source_type == "QUERY_TEMPLATE",
            )
            .group_by(SandboxExperiment.source_id)
            .order_by(func.max(SandboxExperiment.updated_at).desc())
            .limit(200)
        )
        query_options = [{"id": str(source_id), "label": f"Query template {source_id}"} for source_id, _ in result.all()]

    return success_response(
        {
            "experiment_types": sorted(ALLOWED_EXPERIMENT_TYPES),
            "source_types": source_types,
            "source_options": {
                "TRACKING_EVENT": event_options,
                "DATA_QUALITY_RULE": dq_options,
                "PIPELINE": pipeline_options,
                "QUERY_TEMPLATE": query_options,
            },
        }
    )

@router.get("/experiments")
async def list_sandbox_experiments(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    experiment_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_status = _normalize_status(status_filter)
    normalized_type = _normalize_experiment_type(experiment_type) if experiment_type else None
    normalized_source = _normalize_source_type(source_type) if source_type else None

    query = (
        select(SandboxExperiment)
        .where(SandboxExperiment.project_id == context.project.id)
        .order_by(SandboxExperiment.updated_at.desc(), SandboxExperiment.id.desc())
    )
    if normalized_status:
        query = query.where(SandboxExperiment.status == normalized_status)
    if normalized_type:
        query = query.where(SandboxExperiment.experiment_type == normalized_type)
    if normalized_source:
        query = query.where(SandboxExperiment.source_type == normalized_source)
    if q and q.strip():
        like_q = f"%{q.strip()}%"
        query = query.where(
            or_(
                SandboxExperiment.title.ilike(like_q),
                SandboxExperiment.description.ilike(like_q),
                SandboxExperiment.source_id.ilike(like_q),
            )
        )

    result = await db.execute(query)
    rows = list(result.scalars().all())
    total = len(rows)
    items = rows[offset : offset + limit]

    run_map: dict[int, SandboxExperimentRun] = {}
    if items:
        run_result = await db.execute(
            select(SandboxExperimentRun)
            .where(
                SandboxExperimentRun.project_id == context.project.id,
                SandboxExperimentRun.experiment_id.in_([item.id for item in items]),
            )
            .order_by(SandboxExperimentRun.run_no.desc(), SandboxExperimentRun.id.desc())
        )
        for run in run_result.scalars().all():
            if run.experiment_id not in run_map:
                run_map[run.experiment_id] = run

    return success_response(
        {
            "items": [
                {
                    **_experiment_to_row(item),
                    "latest_run": _run_to_row(run_map[item.id]) if item.id in run_map else None,
                }
                for item in items
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": sorted({item.status for item in rows}),
                "experiment_types": sorted({item.experiment_type for item in rows}),
                "source_types": sorted({item.source_type for item in rows}),
            },
        }
    )


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
async def create_sandbox_experiment(
    request: SandboxExperimentCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_experiment_type(request.experiment_type)
    normalized_source = _normalize_source_type(request.source_type)
    if normalized_source not in EXPERIMENT_SOURCE_COMPATIBILITY[normalized_type]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"source_type {normalized_source} incompatible with {normalized_type}")

    baseline = await _resolve_baseline_payload(
        db,
        project_id=context.project.id,
        source_type=normalized_source,
        source_id=request.source_id,
    )
    experiment = await BaseRepository(SandboxExperiment, db).create(
        {
            "project_id": context.project.id,
            "tenant_id": context.project.tenant_id,
            "experiment_type": normalized_type,
            "title": request.title.strip(),
            "description": request.description.strip() if request.description else None,
            "status": "DRAFT",
            "source_type": normalized_source,
            "source_id": request.source_id.strip(),
            "sandbox_source_type": _normalize_source_type(request.sandbox_source_type) if request.sandbox_source_type else normalized_source,
            "sandbox_source_id": request.sandbox_source_id.strip() if request.sandbox_source_id else None,
            "created_by": context.actor_id,
            "created_by_user_id": context.user.id if context.user else None,
            "updated_by": context.actor_id,
            "updated_by_user_id": context.user.id if context.user else None,
            "config_payload": request.config_payload if isinstance(request.config_payload, dict) else {},
            "baseline_payload": baseline,
            "best_candidate_payload": {},
            "conclusion": {"state": "DRAFT", "created_at": _to_iso(datetime.now(timezone.utc))},
        }
    )
    await _write_audit(
        db,
        context,
        "SANDBOX_EXPERIMENT_CREATE",
        experiment,
        {
            "summary": "Sandbox experiment created",
            "experiment_type": normalized_type,
            "source_type": normalized_source,
            "source_id": request.source_id,
            "title": request.title,
        },
    )
    return success_response(_experiment_to_row(experiment), message="Sandbox experiment created", code="SANDBOX_EXPERIMENT_CREATED")


@router.get("/experiments/{experiment_id}")
async def get_sandbox_experiment_detail(
    experiment_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    experiment = await _get_experiment_or_404(db, project_id=context.project.id, experiment_id=experiment_id)
    run_result = await db.execute(
        select(SandboxExperimentRun)
        .where(SandboxExperimentRun.experiment_id == experiment.id)
        .order_by(SandboxExperimentRun.run_no.desc(), SandboxExperimentRun.id.desc())
        .limit(100)
    )
    runs = list(run_result.scalars().all())
    latest = runs[0] if runs else None
    return success_response(
        {
            "experiment": _experiment_to_row(experiment),
            "runs": [_run_to_row(run) for run in runs],
            "latest_run": _run_to_row(latest) if latest else None,
            "navigation": {
                "module_route": SOURCE_ROUTE_MAP.get(experiment.source_type, "/"),
                "source_type": experiment.source_type,
                "source_id": experiment.source_id,
            },
        }
    )

@router.post("/experiments/{experiment_id}/runs")
async def run_sandbox_experiment(
    experiment_id: int,
    request: SandboxExperimentRunRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    experiment = await _get_experiment_or_404(db, project_id=context.project.id, experiment_id=experiment_id)
    if experiment.status == "CANCELLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cancelled experiment cannot be executed")

    run_count_result = await db.execute(
        select(func.count(SandboxExperimentRun.id)).where(SandboxExperimentRun.experiment_id == experiment.id)
    )
    run_no = int(run_count_result.scalar() or 0) + 1

    candidates = _normalize_candidate_payloads(request.candidate_payloads, experiment)
    started_at = datetime.now(timezone.utc)

    await BaseRepository(SandboxExperiment, db).update(
        experiment,
        {
            "status": "RUNNING",
            "updated_by": context.actor_id,
            "updated_by_user_id": context.user.id if context.user else None,
        },
    )

    report_payload, recommendation_payload, best_candidate = _simulate_for_type(
        experiment_type=experiment.experiment_type,
        baseline_payload=experiment.baseline_payload if isinstance(experiment.baseline_payload, dict) else {},
        run_no=run_no,
        sample_size=request.sample_size,
        traffic_ratio=request.traffic_ratio,
        candidates=candidates,
    )

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    run = await BaseRepository(SandboxExperimentRun, db).create(
        {
            "experiment_id": experiment.id,
            "project_id": experiment.project_id,
            "run_no": run_no,
            "status": "COMPLETED",
            "triggered_by": context.actor_id,
            "triggered_by_user_id": context.user.id if context.user else None,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "run_context": {
                "sample_size": request.sample_size,
                "traffic_ratio": request.traffic_ratio,
                "notes": request.notes,
                **request.run_context,
            },
            "report_payload": report_payload,
            "recommendation_payload": recommendation_payload,
        }
    )

    await BaseRepository(SandboxExperiment, db).update(
        experiment,
        {
            "status": "COMPLETED",
            "updated_by": context.actor_id,
            "updated_by_user_id": context.user.id if context.user else None,
            "best_candidate_payload": best_candidate,
            "conclusion": {
                "state": "COMPLETED",
                "latest_run_id": run.id,
                "latest_run_no": run.run_no,
                "best_candidate_key": recommendation_payload.get("best_candidate_key"),
                "best_score": recommendation_payload.get("best_score"),
                "decision": recommendation_payload.get("decision"),
                "reason": recommendation_payload.get("reason"),
                "updated_at": _to_iso(finished_at),
            },
        },
    )

    await _write_audit(
        db,
        context,
        "SANDBOX_EXPERIMENT_RUN",
        experiment,
        {
            "summary": "Sandbox experiment run completed",
            "run_id": run.id,
            "run_no": run.run_no,
            "best_candidate_key": recommendation_payload.get("best_candidate_key"),
            "decision": recommendation_payload.get("decision"),
            "best_score": recommendation_payload.get("best_score"),
            "duration_ms": duration_ms,
        },
    )

    return success_response(
        {
            "experiment": _experiment_to_row(experiment),
            "run": _run_to_row(run),
            "recommendation": recommendation_payload,
        },
        message="Sandbox experiment run completed",
        code="SANDBOX_EXPERIMENT_RUN_COMPLETED",
    )


@router.post("/experiments/{experiment_id}/promote")
async def promote_sandbox_experiment(
    experiment_id: int,
    request: SandboxExperimentPromoteRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    experiment = await _get_experiment_or_404(db, project_id=context.project.id, experiment_id=experiment_id)
    if experiment.status not in {"COMPLETED", "PROMOTED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Experiment must be completed before promotion")

    latest_run = await _latest_experiment_run(db, experiment_id=experiment.id)
    if latest_run is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No run result available for promotion")

    candidate = _extract_candidate_from_run(latest_run, request.candidate_key)
    promotion_result = await _apply_promotion_to_source(db, experiment=experiment, candidate=candidate)
    promoted_at = datetime.now(timezone.utc)

    current_conclusion = experiment.conclusion if isinstance(experiment.conclusion, dict) else {}
    await BaseRepository(SandboxExperiment, db).update(
        experiment,
        {
            "status": "PROMOTED",
            "updated_by": context.actor_id,
            "updated_by_user_id": context.user.id if context.user else None,
            "promote_target_type": promotion_result.get("target_type"),
            "promote_target_id": promotion_result.get("target_id"),
            "promoted_at": promoted_at,
            "best_candidate_payload": candidate,
            "conclusion": {
                **current_conclusion,
                "state": "PROMOTED",
                "promoted_at": _to_iso(promoted_at),
                "promoted_candidate_key": candidate.get("key"),
                "note": request.note,
            },
        },
    )

    await _write_audit(
        db,
        context,
        PROMOTION_ACTION_MAP.get(experiment.source_type, "SANDBOX_EXPERIMENT_PROMOTE"),
        experiment,
        {
            "summary": "Sandbox experiment promoted to production",
            "candidate_key": candidate.get("key"),
            "target_type": promotion_result.get("target_type"),
            "target_id": promotion_result.get("target_id"),
            "route": promotion_result.get("route"),
            "note": request.note,
        },
    )

    return success_response(
        {
            "experiment": _experiment_to_row(experiment),
            "promoted_candidate": candidate,
            "promotion_target": promotion_result,
        },
        message="Sandbox experiment promoted",
        code="SANDBOX_EXPERIMENT_PROMOTED",
    )
