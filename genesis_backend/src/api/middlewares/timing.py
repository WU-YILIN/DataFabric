import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from src.utils.logger import get_logger

logger = get_logger(__name__)

class ProcessTimeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        logger.info(
            "Request processed",
            path=request.url.path,
            method=request.method,
            duration=process_time
        )
        return response
