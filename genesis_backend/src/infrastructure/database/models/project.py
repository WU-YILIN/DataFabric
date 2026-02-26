from sqlalchemy import String, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.database.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    tech_stack: Mapped[dict] = mapped_column(JSON, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="projects")
    events: Mapped[list["TrackingEvent"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    pipelines: Mapped[list["Pipeline"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    data_assets: Mapped[list["DataAsset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    data_quality_rules: Mapped[list["DataQualityRule"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    scheduler_dags: Mapped[list["SchedulerDag"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    scheduler_runs: Mapped[list["SchedulerRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    user_roles: Mapped[list["UserProjectRole"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    integration_settings: Mapped[list["ProjectIntegrationSetting"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    integration_invocation_logs: Mapped[list["IntegrationInvocationLog"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    member_invitations: Mapped[list["ProjectMemberInvitation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    collaboration_workflows: Mapped[list["CollaborationWorkflow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    sandbox_experiments: Mapped[list["SandboxExperiment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    policy_rules: Mapped[list["PolicyRule"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    ingestion_channels: Mapped[list["IngestionChannelConfig"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    ingestion_event_logs: Mapped[list["IngestionEventLog"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    release_changes: Mapped[list["ReleaseChangeRequest"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    custom_report_dashboards: Mapped[list["CustomReportDashboard"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    data_products: Mapped[list["DataProduct"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    incident_cases: Mapped[list["IncidentCase"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}')>"
