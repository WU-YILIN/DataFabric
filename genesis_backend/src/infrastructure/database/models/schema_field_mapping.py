"""
Module 2 — 契约元数据中心
SchemaFieldMapping：存储从原始 JSON 字段路径到标准契约字段的映射规则。

生命周期：
  PENDING  ← 由 Celery 扫描任务 / AI 探针自动创建（尚未审批）
  APPROVED ← 人工管理员审批通过 → 触发 ViewCompiler 重编译虚拟视图
  REJECTED ← 人工审批拒绝
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class FieldMappingStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FieldCastType:
    FLOAT = "FLOAT"
    INT = "INT"
    STRING = "STRING"
    BOOL = "BOOL"


class SchemaFieldMapping(Base, TimestampMixin):
    """
    映射规则表：一条记录 = 一个标准契约字段对应的全部原始字段可能路径。

    示例：
      event_id    = 5 (checkout 事件)
      target_field = "price"
      source_paths = ["$.price", "$.zhifu_jine", "$.payment_info.amount_total"]
      cast_type    = "FLOAT"
      status       = "APPROVED"

    ViewCompiler 会把上面这条规则翻译成：
      CAST(COALESCE(
        json_extract(raw_payload, '$.price'),
        json_extract(raw_payload, '$.zhifu_jine'),
        json_extract(raw_payload, '$.payment_info.amount_total')
      ) AS REAL) AS price
    """

    __tablename__ = "schema_field_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 所属项目 & 事件
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("tracking_events.id"), nullable=False, index=True
    )

    # 目标字段（标准契约中的字段名）
    target_field: Mapped[str] = mapped_column(String(128), nullable=False)

    # 来源路径列表（JSONPath 字符串数组），存 JSON
    source_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # 类型转换目标：FLOAT / INT / STRING / BOOL
    cast_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FieldCastType.STRING
    )

    # 审批状态
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FieldMappingStatus.PENDING, index=True
    )

    # AI 置信度（0.0~1.0）；人工创建时为 1.0
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )

    # 谁发起的：'ai' 或 'human' 或 'scanner'
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False, default="scanner")

    # 审批者（用户 Email 或 ID）
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI 建议的推理依据
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 影子测试结果：审批前做 dry-run 的指标偏离 %（防止误批）
    shadow_delta_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 拒绝原因 / 备注
    note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # 事件出现频率（扫描任务采集，辅助排优先级）
    field_frequency: Mapped[int] = mapped_column(nullable=False, default=0)

    # 外键关系（只读引用，不级联删除）
    project: Mapped["Project"] = relationship(foreign_keys=[project_id])
    event: Mapped["TrackingEvent"] = relationship(foreign_keys=[event_id])

    # 复合唯一索引：同一事件的同一目标字段只允许有一条 APPROVED 规则
    __table_args__ = (
        Index("uq_mapping_event_target", "event_id", "target_field"),
    )

    def __repr__(self) -> str:
        return (
            f"<SchemaFieldMapping(event_id={self.event_id}, "
            f"target='{self.target_field}', status='{self.status}')>"
        )
