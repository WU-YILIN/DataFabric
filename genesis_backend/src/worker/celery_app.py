from celery import Celery
from src.config import settings

celery_app = Celery(
    "genesis_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.worker.tasks.code_scanner", "src.worker.tasks.ingestion"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
