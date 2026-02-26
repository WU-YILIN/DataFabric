from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SchedulerDagEdge(Base, TimestampMixin):
    __tablename__ = "scheduler_dag_edges"
    __table_args__ = (UniqueConstraint("dag_id", "from_node_id", "to_node_id", name="uq_scheduler_dag_edge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dag_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dags.id"), nullable=False)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dag_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dag_nodes.id"), nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    dag: Mapped["SchedulerDag"] = relationship(back_populates="edges")
    from_node: Mapped["SchedulerDagNode"] = relationship(
        "SchedulerDagNode", foreign_keys=[from_node_id]
    )
    to_node: Mapped["SchedulerDagNode"] = relationship("SchedulerDagNode", foreign_keys=[to_node_id])

    def __repr__(self) -> str:
        return (
            f"<SchedulerDagEdge(id={self.id}, dag_id={self.dag_id}, "
            f"from_node_id={self.from_node_id}, to_node_id={self.to_node_id})>"
        )
