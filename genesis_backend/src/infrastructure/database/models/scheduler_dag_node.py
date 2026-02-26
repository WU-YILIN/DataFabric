from sqlalchemy import Boolean, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SchedulerDagNode(Base, TimestampMixin):
    __tablename__ = "scheduler_dag_nodes"
    __table_args__ = (UniqueConstraint("dag_id", "node_key", name="uq_scheduler_dag_node_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dag_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dags.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input_assets: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    output_assets: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    logic_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    position: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    dag: Mapped["SchedulerDag"] = relationship(back_populates="nodes")
    run_records: Mapped[list["SchedulerNodeRun"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SchedulerDagNode(id={self.id}, dag_id={self.dag_id}, node_key='{self.node_key}')>"
