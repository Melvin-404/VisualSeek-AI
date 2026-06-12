"""LLM-powered intent extraction for surveillance queries.

Defines the SearchIntent data model and the IntentExtractor class that
calls OpenAI / Anthropic / Llama APIs to convert free-text queries into
structured search parameters.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger("nl_query.intent")

# Prompt files live alongside this module
_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Token costs in USD per 1K tokens (approximate, as of 2024-Q4)
_MODEL_COSTS: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
}


@dataclass
class SearchIntent:
    """Structured search intent extracted from a natural language query."""

    intent_type: str = "object_search"  # object_search | event_search | statistical_query | comparison
    object_class: Optional[str] = None
    attributes: List[str] = field(default_factory=list)
    color: Optional[str] = None
    time_range: Optional[Dict[str, Any]] = None
    camera_ids: List[str] = field(default_factory=list)
    event_type: Optional[str] = None
    spatial_zone: Optional[str] = None
    negations: List[str] = field(default_factory=list)
    unstructured_fallback: bool = False
    rewritten_query: str = ""
    llm_cost: float = 0.0
    raw_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "intent_type": self.intent_type,
            "object_class": self.object_class,
            "attributes": self.attributes,
            "color": self.color,
            "time_range": self.time_range,
            "camera_ids": self.camera_ids,
            "event_type": self.event_type,
            "spatial_zone": self.spatial_zone,
            "negations": self.negations,
            "unstructured_fallback": self.unstructured_fallback,
            "rewritten_query": self.rewritten_query,
            "llm_cost": self.llm_cost,
        }


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.error("Prompt file not found.", path=str(path))
        return ""


class IntentExtractor:
    """Extracts structured SearchIntent from a query using LLM APIs.

    Supports OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet), and
    local Llama via OpenAI-compatible endpoints.
    """

    def __init__(self):
        self._system_prompt = _load_prompt("intent_system.txt")
        self._fewshot_prompt = _load_prompt("intent_fewshot.txt")
        self._provider = settings.LLM_PROVIDER.lower()
        self._timeout = settings.LLM_TIMEOUT
        self._max_retries = settings.LLM_MAX_RETRIES

    async def extract(self, query: str, entity_context: str = "") -> SearchIntent:
        """Run LLM intent extraction with retries and cost tracking.

        Args:
            query: The raw user query.
            entity_context: Pre-extracted entity context string from SpaCyEntityExtractor.

        Returns:
            SearchIntent populated from LLM output.

        Raises:
            IntentExtractionError: If all retries fail.
        """
        user_message = self._build_user_prompt(query, entity_context)

        for attempt in range(1, self._max_retries + 1):
            try:
                if self._provider == "openai":
                    return await self._call_openai(query, user_message)
                elif self._provider == "anthropic":
                    return await self._call_anthropic(query, user_message)
                elif self._provider == "llama":
                    return await self._call_llama(query, user_message)
                else:
                    raise IntentExtractionError(f"Unknown LLM provider: {self._provider}")
            except IntentExtractionError:
                raise
            except Exception as e:
                logger.warning(
                    "LLM extraction attempt failed.",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    provider=self._provider,
                    error=str(e),
                )
                if attempt == self._max_retries:
                    raise IntentExtractionError(
                        f"All {self._max_retries} LLM attempts failed: {e}"
                    ) from e
                time.sleep(0.5 * attempt)  # simple back-off

        # Should not reach here
        raise IntentExtractionError("Extraction loop exited without result.")

    def _build_user_prompt(self, query: str, entity_context: str) -> str:
        """Compose the user message for the LLM."""
        parts = [f'User query: "{query}"']
        if entity_context:
            parts.append(f"\nPre-extracted entities: {entity_context}")
        parts.append("\nReturn ONLY the JSON object. No explanation or markdown.")
        return "\n".join(parts)

    async def _call_openai(self, raw_query: str, user_message: str) -> SearchIntent:
        """Call OpenAI's chat completions API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=self._timeout,
        )
        model = settings.LLM_MODEL_OPENAI

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._fewshot_prompt + "\n\n---\n\n" + user_message},
        ]

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        cost = self._compute_cost(
            model,
            response.usage.prompt_tokens if response.usage else 0,
            response.usage.completion_tokens if response.usage else 0,
        )

        return self._parse_response(content, raw_query, cost)

    async def _call_anthropic(self, raw_query: str, user_message: str) -> SearchIntent:
        """Call Anthropic's messages API."""
        import anthropic

        client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=self._timeout,
        )
        model = settings.LLM_MODEL_ANTHROPIC

        response = await client.messages.create(
            model=model,
            system=self._system_prompt,
            messages=[
                {"role": "user", "content": self._fewshot_prompt + "\n\n---\n\n" + user_message},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content = block.text
                break

        cost = self._compute_cost(
            model,
            response.usage.input_tokens if response.usage else 0,
            response.usage.output_tokens if response.usage else 0,
        )

        return self._parse_response(content, raw_query, cost)

    async def _call_llama(self, raw_query: str, user_message: str) -> SearchIntent:
        """Call a local Llama model via OpenAI-compatible API."""
        from openai import AsyncOpenAI

        base_url = settings.LLAMA_API_URL
        if not base_url:
            raise IntentExtractionError("LLAMA_API_URL not configured")

        client = AsyncOpenAI(
            api_key="local",  # Llama servers typically don't need a real key
            base_url=base_url,
            timeout=self._timeout,
        )
        model = settings.LLM_MODEL_LLAMA

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._fewshot_prompt + "\n\n---\n\n" + user_message},
        ]

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
        )

        content = response.choices[0].message.content or "{}"
        # Local models are free
        return self._parse_response(content, raw_query, cost=0.0)

    def _parse_response(self, content: str, raw_query: str, cost: float) -> SearchIntent:
        """Parse LLM JSON response into a SearchIntent."""
        # Extract JSON from possible markdown code blocks
        content = content.strip()
        if content.startswith("```"):
            # Remove markdown fences
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response.", error=str(e), content=content[:200])
            raise IntentExtractionError(f"Invalid JSON from LLM: {e}") from e

        return SearchIntent(
            intent_type=data.get("intent_type", "object_search"),
            object_class=data.get("object_class"),
            attributes=data.get("attributes", []),
            color=data.get("color"),
            time_range=data.get("time_range"),
            camera_ids=data.get("camera_ids", []),
            event_type=data.get("event_type"),
            spatial_zone=data.get("spatial_zone"),
            negations=data.get("negations", []),
            unstructured_fallback=False,
            rewritten_query=data.get("rewritten_query", raw_query),
            llm_cost=cost,
            raw_query=raw_query,
        )

    @staticmethod
    def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Compute approximate API cost in USD."""
        costs = _MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        return round(
            (input_tokens / 1000.0) * costs["input"]
            + (output_tokens / 1000.0) * costs["output"],
            6,
        )


class IntentExtractionError(Exception):
    """Raised when LLM intent extraction fails after all retries."""

    pass
