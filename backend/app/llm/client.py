"""LLM abstraction layer supporting none, anthropic, and ollama using httpx only.
Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
import httpx
from pydantic import ValidationError

from app.config import settings
from app.llm.schemas import AIExtractionOutput, VALID_TYPOLOGIES

logger = logging.getLogger("cryptotrace.llm")

EXTRACTION_SYSTEM_PROMPT = """You are a forensic legal intake assistant for Indian Cyber Crime Law Enforcement (MHA / I4C).
Your task is to analyze the victim's complaint text and extract verifiable facts into strict JSON.

CRITICAL GUARDRAIL RULES:
1. NEVER invent, hallucinate, or extrapolate facts, amounts, or entities.
2. For EVERY extracted fact, you MUST provide an "evidence_quote" which is an EXACT substring from the complaint text.
3. If an offence date, amount, entity, or loss is not clearly stated in the text, leave it as null/empty list.
4. "suggested_typology" MUST strictly be one of:
   - "investment_scam"
   - "phishing_impersonation"
   - "hack_theft"
   - "ransomware_extortion"
   - "sextortion"
   - "insider_misappropriation"
   - "layering_laundering"
   or null if no clear match.
5. Provide a clear English translation if the text is non-English (e.g. Hindi), and a concise neutral summary.
6. Output ONLY valid JSON matching this schema:
{
  "offence_date": "YYYY-MM-DD or null",
  "offence_date_quote": "exact quote from text or null",
  "amounts": [{"amount": 1000.0, "currency": "INR", "evidence_quote": "exact quote"}],
  "victim_loss_inr": 1000.0,
  "victim_loss_quote": "exact quote from text or null",
  "entities_referenced": [{"name": "Binance", "category": "exchange", "evidence_quote": "exact quote"}],
  "suggested_typology": "investment_scam or null",
  "typology_quote": "exact quote from text or null",
  "translation_en": "English translation or null",
  "summary": "Short neutral factual summary"
}
"""


class LLMClient(ABC):
    """Abstract base class for LLM extraction providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def extract_complaint_facts(
        self, masked_text: str, language: Optional[str] = None
    ) -> Tuple[Optional[AIExtractionOutput], Optional[str]]:
        """Extract structured facts from complaint text.
        Returns: (AIExtractionOutput or None, failure_reason or None)
        """
        pass


class NoneLLMClient(LLMClient):
    """Deterministic mode client when LLM_PROVIDER is none."""

    @property
    def provider_name(self) -> str:
        return "none"

    def extract_complaint_facts(
        self, masked_text: str, language: Optional[str] = None
    ) -> Tuple[Optional[AIExtractionOutput], Optional[str]]:
        return None, "Running in deterministic mode (LLM_PROVIDER=none)."


class AnthropicClient(LLMClient):
    """Anthropic Claude API client using httpx only."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL") or getattr(settings, "LLM_MODEL", "") or "claude-3-5-sonnet-latest"
        self.timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _call_api(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured in environment.")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "system": EXTRACTION_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            return "\n".join(text_parts).strip()

    def extract_complaint_facts(
        self, masked_text: str, language: Optional[str] = None
    ) -> Tuple[Optional[AIExtractionOutput], Optional[str]]:
        user_prompt = f"Analyze the following complaint text:\n\n{masked_text}"
        try:
            raw_output = self._call_api(user_prompt)
            return self._parse_json_with_retry(raw_output, user_prompt)
        except Exception as e:
            logger.warning(f"Anthropic extraction failed: {e}")
            return None, f"Anthropic error: {str(e)}"

    def _parse_json_with_retry(
        self, raw_text: str, original_prompt: str
    ) -> Tuple[Optional[AIExtractionOutput], Optional[str]]:
        # Attempt 1: Parse directly
        parsed = _clean_and_parse_json(raw_text)
        if parsed:
            try:
                validated = AIExtractionOutput.model_validate(parsed)
                return validated, None
            except ValidationError as ve:
                logger.info(f"Validation error on attempt 1: {ve}")

        # Attempt 2: One retry with correction
        retry_prompt = (
            f"{original_prompt}\n\nYour previous response was not valid JSON or failed schema validation: "
            f"{raw_text}\n\nReturn strictly valid JSON only matching the schema."
        )
        try:
            retry_raw = self._call_api(retry_prompt)
            parsed_retry = _clean_and_parse_json(retry_raw)
            if parsed_retry:
                validated = AIExtractionOutput.model_validate(parsed_retry)
                return validated, None
        except Exception as e:
            return None, f"JSON validation failed after retry: {e}"

        return None, "Failed to parse valid JSON from model response."


class OllamaClient(LLMClient):
    """Local Ollama client using httpx only."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_URL") or getattr(settings, "OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or getattr(settings, "LLM_MODEL", "") or "llama3.2"
        self.timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "ollama"

    def _call_api(self, prompt: str) -> str:
        endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()

    def extract_complaint_facts(
        self, masked_text: str, language: Optional[str] = None
    ) -> Tuple[Optional[AIExtractionOutput], Optional[str]]:
        user_prompt = f"Analyze the following complaint text:\n\n{masked_text}"
        try:
            raw_output = self._call_api(user_prompt)
            parsed = _clean_and_parse_json(raw_output)
            if parsed:
                try:
                    return AIExtractionOutput.model_validate(parsed), None
                except ValidationError:
                    pass

            # One retry
            retry_prompt = (
                f"{user_prompt}\n\nYour previous response was not valid JSON: {raw_output}. "
                f"Respond with strictly valid JSON only."
            )
            raw_retry = self._call_api(retry_prompt)
            parsed_retry = _clean_and_parse_json(raw_retry)
            if parsed_retry:
                return AIExtractionOutput.model_validate(parsed_retry), None
            return None, "Failed to parse JSON output from Ollama."
        except Exception as e:
            logger.warning(f"Ollama extraction failed: {e}")
            return None, f"Ollama error: {str(e)}"


def _clean_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Clean markdown code fences and parse JSON object."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        # Search for first { and last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                pass
        return None


def get_llm_client(provider_override: Optional[str] = None) -> LLMClient:
    """Factory creating appropriate LLMClient based on environment or override."""
    provider = (
        provider_override
        or os.getenv("LLM_PROVIDER")
        or getattr(settings, "LLM_PROVIDER", "none")
    ).lower()

    if provider == "anthropic":
        return AnthropicClient()
    elif provider == "ollama":
        return OllamaClient()
    else:
        return NoneLLMClient()
