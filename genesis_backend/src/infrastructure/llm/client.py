import json
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
    model_name: str = Field(default="")


class LLMAdapter:
    def __init__(self):
        client_kwargs: dict = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL
        self.client = AsyncOpenAI(**client_kwargs)
        self.model = settings.OPENAI_MODEL

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def arbitrate(self, prompt: str) -> ArbitrationResponse:
        logger.info("Sending request to LLM", model=self.model)
        try:
            # Use regular chat completion with JSON instruction
            # (compatible with all OpenAI-compatible APIs)
            system_prompt = (
                "You are a data governance arbiter. "
                "Respond ONLY with valid JSON matching this schema:\n"
                '{"verdict": "APPROVE|REJECT|NEEDS_REVISION", "score": 0.0-1.0, '
                '"reasoning": "...", "recommended_code": "...|null", '
                '"risks": ["..."], "suggestions": [{"title":"...","rationale":"...","patch":{}}], '
                '"model_name": "..."}'
            )
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )
            raw = response.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            if raw.strip().startswith("```"):
                lines = raw.strip().split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines)

            data = json.loads(raw)
            if not data.get("model_name"):
                data["model_name"] = self.model
            return ArbitrationResponse.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error("LLM returned invalid JSON", error=str(e), raw=raw[:500])
            # Return a safe fallback
            return ArbitrationResponse(
                verdict="NEEDS_REVISION",
                score=0.5,
                reasoning=f"LLM returned non-JSON response. Raw: {raw[:200]}",
                model_name=self.model,
            )
        except Exception as e:
            logger.error("LLM request failed", error=str(e))
            raise
