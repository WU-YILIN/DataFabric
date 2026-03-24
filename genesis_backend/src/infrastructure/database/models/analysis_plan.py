from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin


class AnalysisPlan(Base, TimestampMixin):
    __tablename__ = "analysis_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(nullable=True)
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="GENERATED")
    question_weight: Mapped[str] = mapped_column(String(32), nullable=False, default="LIGHT")
    metric_candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_requirements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_bundle: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_service_plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    collaboration_workflow_id: Mapped[int | None] = mapped_column(
        ForeignKey("collaboration_workflows.id"),
        nullable=True,
    )
