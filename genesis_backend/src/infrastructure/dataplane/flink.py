import httpx

from src.config import settings
from src.domain.exceptions import AppError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FlinkProvisioner:
    async def deploy_pipeline_job(self, job_name: str, topic_name: str) -> dict:
        if settings.PIPELINE_PROVISION_MODE == "mock":
            logger.info(
                "Flink job deployed (mock)",
                job_name=job_name,
                topic=topic_name,
                flink_rest_url=settings.FLINK_REST_URL,
            )
            return {"job_name": job_name, "topic": topic_name, "state": "RUNNING", "job_id": f"mock-{job_name}"}

        jar_id = settings.FLINK_PIPELINE_JAR_ID
        entry_class = settings.FLINK_PIPELINE_ENTRY_CLASS
        if not jar_id or not entry_class:
            raise AppError(
                "Flink real mode requires FLINK_PIPELINE_JAR_ID and FLINK_PIPELINE_ENTRY_CLASS",
                code="FLINK_CONFIG_MISSING",
                status_code=500,
            )

        async with httpx.AsyncClient(base_url=settings.FLINK_REST_URL, timeout=20.0) as client:
            overview = await client.get("/overview")
            if overview.status_code >= 400:
                raise AppError(
                    f"Flink unavailable: {overview.text}",
                    code="FLINK_UNAVAILABLE",
                    status_code=502,
                )

            run_resp = await client.post(
                f"/jars/{jar_id}/run",
                json={
                    "entryClass": entry_class,
                    "programArgsList": [
                        "--jobName",
                        job_name,
                        "--topic",
                        topic_name,
                    ],
                },
            )
            if run_resp.status_code >= 400:
                raise AppError(
                    f"Flink submit failed: {run_resp.text}",
                    code="FLINK_SUBMIT_FAILED",
                    status_code=502,
                )

            job_id = run_resp.json().get("jobid")
            if not job_id:
                raise AppError(
                    "Flink submit succeeded but no job id returned",
                    code="FLINK_JOBID_MISSING",
                    status_code=502,
                )

        logger.info("Flink job deployed", job_name=job_name, topic=topic_name, job_id=job_id)
        return {"job_name": job_name, "topic": topic_name, "state": "RUNNING", "job_id": job_id}

    async def stop_pipeline_job(self, job_name: str, job_id: str | None = None) -> None:
        if settings.PIPELINE_PROVISION_MODE == "mock":
            logger.info("Flink job stopped (mock)", job_name=job_name)
            return

        if not job_id:
            raise AppError(
                "Flink job id is required for stop in real mode",
                code="FLINK_JOBID_REQUIRED",
                status_code=400,
            )

        async with httpx.AsyncClient(base_url=settings.FLINK_REST_URL, timeout=20.0) as client:
            stop_resp = await client.patch(f"/jobs/{job_id}", params={"mode": "cancel"})
            if stop_resp.status_code >= 400:
                raise AppError(
                    f"Flink stop failed: {stop_resp.text}",
                    code="FLINK_STOP_FAILED",
                    status_code=502,
                )

        logger.info("Flink job stopped", job_name=job_name, job_id=job_id)

    async def get_job_state(self, job_id: str) -> str:
        if settings.PIPELINE_PROVISION_MODE == "mock":
            return "RUNNING"

        async with httpx.AsyncClient(base_url=settings.FLINK_REST_URL, timeout=20.0) as client:
            resp = await client.get(f"/jobs/{job_id}")
            if resp.status_code >= 400:
                raise AppError(
                    f"Flink job state query failed: {resp.text}",
                    code="FLINK_STATE_QUERY_FAILED",
                    status_code=502,
                )
            state = resp.json().get("state")
            if not state:
                raise AppError(
                    "Flink state response missing state field",
                    code="FLINK_STATE_MISSING",
                    status_code=502,
                )
            return state
