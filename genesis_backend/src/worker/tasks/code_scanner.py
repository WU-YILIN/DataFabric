from src.worker.celery_app import celery_app
from src.utils.logger import get_logger
import time

logger = get_logger(__name__)

@celery_app.task(name="scan_repository_for_events")
def scan_repository_for_events(repo_url: str, branch: str = "main"):
    logger.info("Starting repository scan", repo_url=repo_url, branch=branch)
    
    # Simulate work
    time.sleep(5)
    
    found_events = [
        {"code": "evt_user_login", "line": 42},
        {"code": "evt_purchase_complete", "line": 128}
    ]
    
    logger.info("Scan completed", found_count=len(found_events))
    return {"status": "completed", "found_events": found_events}
