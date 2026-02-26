from typing import List, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GOVERNANCE_MODEL = "gpt-4o-mini"


class GovernanceSuggestion(BaseModel):
    title: str
    rationale: str
    patch: dict = Field(default_factory=dict)


class ArbitrationResponse(BaseModel):
    verdict: str = Field(..., pattern="^(APPROVE|REJECT|NEEDS_REVISION)$")
    score: float = Field(..., ge=0, le=1)
    reasoning: str
    recommended_code: Optional[str] = None
    risks: list[str] = Field(default_factory=list)
    suggestions: list[GovernanceSuggestion] = Field(default_factory=list)
    model_name: str = Field(default=DEFAULT_GOVERNANCE_MODEL)


class LLMAdapter:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def arbitrate(self, prompt: str) -> ArbitrationResponse:
        logger.info("Sending request to LLM")
        try:
            response = await self.client.beta.chat.completions.parse(
                model=DEFAULT_GOVERNANCE_MODEL,
                messages=[
                    {"role": "system", "content": "You are a data governance arbiter."},
                    {"role": "user", "content": prompt}
                ],
                response_format=ArbitrationResponse,
            )
            parsed = response.choices[0].message.parsed
            if not parsed.model_name:
                parsed.model_name = DEFAULT_GOVERNANCE_MODEL
            return parsed
        except Exception as e:
            logger.error("LLM request failed", error=str(e))
            raise
