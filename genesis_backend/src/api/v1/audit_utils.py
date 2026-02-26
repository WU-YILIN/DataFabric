from sqlalchemy import or_

from src.infrastructure.database.models.audit import AuditLog


def build_project_audit_filter(project_id: int):
    return or_(
        AuditLog.user_id == f"project_{project_id}",
        AuditLog.user_id == f"project:{project_id}",
        AuditLog.user_id.like(f"%|project:{project_id}"),
    )


def parse_actor(actor_id: str | None) -> str:
    if not actor_id:
        return "unknown"
    if actor_id.startswith("user:"):
        return actor_id.split("|", maxsplit=1)[0].removeprefix("user:")
    if actor_id.startswith("project:"):
        return actor_id.replace("project:", "project_")
    return actor_id
