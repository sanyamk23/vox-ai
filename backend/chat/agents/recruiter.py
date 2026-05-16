from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import aiohttp
from google import genai
from google.genai import types

from .base import BaseAgent
from .schemas import InterviewContext

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")

_JD_PARSE_SYSTEM = """\
You are an expert talent acquisition analyst. Parse the job description and return structured JSON.

Return ONLY valid JSON — no markdown fences, no extra text:
{
  "job_title": "<title from JD or best inference>",
  "company_name": "<company name, or empty string if not mentioned>",
  "required_skills": ["<skill1>", "<skill2>"],
  "nice_to_have_skills": ["<skill1>"],
  "experience_level": "<junior|mid|senior|lead|principal>",
  "domain": "<fintech|edtech|healthtech|ecommerce|SaaS|infra|general>",
  "custom_questions": [
    "<natural probe question targeting a specific JD requirement>",
    "<natural probe question targeting another JD requirement>",
    "<natural probe question targeting another JD requirement>"
  ],
  "phase_weights": {
    "exploration": 1.0,
    "motivation": 1.0,
    "logistics": 1.0
  }
}

Rules for custom_questions (max 3):
- Target a specific JD skill or requirement each time
- Conversational, not robotic — sound like a recruiter asking naturally
- Good: "What's the largest Kubernetes cluster you've managed, like in terms of nodes?"
- Bad:  "Can you describe your experience with container orchestration using Kubernetes?"

Rules for phase_weights (values 0.5–2.0, default 1.0):
- Senior/principal/staff: exploration=1.5 (deeper technical probing)
- Startup/product/founding: motivation=1.5 (culture fit matters more)
- Logistics-heavy JDs (contract, relocation): logistics=1.5
- Default to 1.0 when unsure — never set below 0.5
"""


class RecruiterAgent(BaseAgent):
    """
    Phase 1 — Pre-call.
    Parses the JD and builds an InterviewContext for the OrchestratorAgent.
    Launches background company intel fetch (fire-and-forget) if company_name is found.

    Guardrails:
    - JD < 20 chars  → immediate fallback (no LLM call)
    - LLM timeout    → 1 retry, then fallback
    - Bad JSON       → fallback
    - Fallback       → InterviewContext(raw_jd=jd, recruiter_status="fallback_used")
                       preserves current system behavior exactly
    """

    name = "recruiter"
    timeout_seconds = 8.0
    max_retries = 1

    def __init__(self, gemini_client: genai.Client) -> None:
        super().__init__()
        self.gemini = gemini_client

    # ------------------------------------------------------------------
    # BaseAgent implementation
    # ------------------------------------------------------------------

    async def _execute(self, jd: str, candidate_name: str = "") -> InterviewContext:
        if not jd or len(jd.strip()) < 20:
            logger.warning("[Recruiter] JD too short (%d chars) — using fallback", len(jd or ""))
            return self._fallback(jd, candidate_name)

        prompt = f"{_JD_PARSE_SYSTEM}\n\nParse this JD:\n\n{jd[:3000]}"
        resp = await self.gemini.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=700,
            ),
        )

        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)

        ctx = InterviewContext(
            job_title=data.get("job_title", "Software Engineer"),
            company_name=data.get("company_name", ""),
            required_skills=(data.get("required_skills") or [])[:10],
            nice_to_have_skills=(data.get("nice_to_have_skills") or [])[:5],
            experience_level=data.get("experience_level", "mid"),
            domain=data.get("domain", ""),
            custom_questions=(data.get("custom_questions") or [])[:3],
            phase_weights=data.get("phase_weights") or {},
            raw_jd=jd,
            recruiter_status="completed",
        )
        logger.info(
            "[Recruiter] Parsed JD → title=%r skills=%s level=%s",
            ctx.job_title, ctx.required_skills[:3], ctx.experience_level,
        )
        return ctx

    def _fallback(self, jd: str = "", candidate_name: str = "", **_) -> InterviewContext:
        """Minimal context from raw JD — identical to pre-refactor behaviour."""
        return InterviewContext(
            raw_jd=jd or "",
            recruiter_status="fallback_used",
        )

    # ------------------------------------------------------------------
    # Background intel (fire-and-forget, never raises)
    # ------------------------------------------------------------------

    async def fetch_background_intel(self, company_name: str) -> dict:
        """
        Fetches basic public company info and returns it.
        Always returns a dict (empty on failure) — never raises.
        Caller should run this via asyncio.create_task() to avoid blocking.
        """
        if not company_name:
            return {}
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            slug = company_name.strip().replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "description": (data.get("extract") or "")[:600],
                            "source": "wikipedia",
                        }
        except Exception as exc:
            logger.debug("[Recruiter-Intel] Silent failure for %r: %s", company_name, exc)
        return {}
