from src.worker.celery_app import celery_app
from src.utils.logger import get_logger
import time

logger = get_logger(__name__)

@celery_app.task(name="ingest_csv_batch")
def ingest_csv_batch(file_path: str):
    logger.info("Starting batch ingestion", file_path=file_path)
    
    # Simulate processing 10,000 rows
    for i in range(10):
        time.sleep(1)
        logger.info(f"Processed { (i+1) * 10 }%")
        
    logger.info("Ingestion completed")
    return {"status": "success", "processed_rows": 10000}
