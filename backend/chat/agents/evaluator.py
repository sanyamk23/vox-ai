from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from google import genai
from google.genai import types

from .base import BaseAgent
from .schemas import EvalDimension, EvalReport, InterviewContext

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")
_VALID_OUTCOMES = {"INTERESTED", "BUSY", "NOT_INTERESTED", "CALLBACK_REQUESTED", "CONFUSED"}

_EVAL_SYSTEM = """\
You are a senior HR analytics expert. Evaluate this screening call and produce a structured assessment.

Return ONLY valid JSON — no markdown fences, no extra text:
{
  "intent_score": <integer 1-10 — 10=extremely excited, 1=clearly not interested>,
  "call_outcome": "<INTERESTED|BUSY|NOT_INTERESTED|CALLBACK_REQUESTED|CONFUSED>",
  "technical_fit": {
    "score": <1-10>,
    "confidence": <0.0-1.0>,
    "evidence": ["<direct quote or observed signal>"]
  },
  "communication": {
    "score": <1-10>,
    "confidence": <0.0-1.0>,
    "evidence": ["<e.g. articulate, concise, struggled with English>"]
  },
  "motivation_fit": {
    "score": <1-10>,
    "confidence": <0.0-1.0>,
    "evidence": ["<why they're looking, what they want next>"]
  },
  "logistics_fit": {
    "score": <1-10>,
    "confidence": <0.0-1.0>,
    "evidence": ["<salary, notice period, competing offers>"]
  },
  "overall_confidence": <0.0-1.0>,
  "summary_bullets": ["<3-5 specific bullets quoting actual things said>"],
  "skills_verified": ["<skills the candidate explicitly confirmed>"],
  "salary_expectation_lpa": <number or null>,
  "current_ctc_lpa": <number or null>,
  "notice_period_days": <number or null — 1 month=30, 2 months=60, immediate=0>,
  "joining_timeline": "<candidate's own words or null>",
  "other_offers": <true/false/null>,
  "hr_flags": ["<specific red flags — empty array if none>"],
  "vibe_check": "<one honest sentence about the candidate's energy and fit>",
  "recommended_next_step": "<specific action for the hiring team>",
  "reasoning": "<2-3 sentences explaining the score and outcome decision>"
}

Evaluation rules:
- Base EVERY field strictly on what was actually said — use null if not discussed
- Never infer or fabricate
- technical_fit.confidence must be LOW (<0.4) for short or surface-level calls
- overall_confidence < 0.4 means insufficient data — add a flag in hr_flags
- hr_flags must include: salary mismatch vs JD range, notice > 90 days, strong competing offers, evasive answers
- Outcome decision guide:
    technical_fit.score < 4                          → NOT_INTERESTED
    logistics mismatch (salary, location, notice)    → CALLBACK_REQUESTED
    intent_score >= 7 AND technical_fit.score >= 6   → INTERESTED
    candidate was unavailable / busy                 → BUSY
    when in doubt                                    → CONFUSED
"""


class EvaluationAgent(BaseAgent):
    """
    Phase 3 — Post-call.
    Scores the candidate across four dimensions and produces an EvalReport.

    Guardrails:
    - LLM timeout / bad JSON  → up to 2 retries, then fallback
    - Fallback                → EvalReport built from live_notes captured during call
                                (skills, salary, notice) — no data loss
    """

    name = "evaluator"
    timeout_seconds = 20.0   # post-call, no latency pressure
    max_retries = 2

    def __init__(
        self,
        gemini_client: genai.Client,
        interview_context: Optional[InterviewContext] = None,
    ) -> None:
        super().__init__()
        self.gemini = gemini_client
        self.interview_context = interview_context

    # ------------------------------------------------------------------
    # BaseAgent implementation
    # ------------------------------------------------------------------

    async def _execute(
        self,
        transcript: list,
        live_notes: dict,
        context: InterviewContext,
    ) -> EvalReport:
        self.interview_context = context

        user_content = (
            f"{self._format_jd_context(context)}\n\n"
            f"Live notes captured during call:\n"
            f"{json.dumps(live_notes, indent=2)}\n\n"
            f"Full transcript:\n{self._format_transcript(transcript)}"
        )
        prompt = f"{_EVAL_SYSTEM}\n\n{user_content}"

        resp = await self.gemini.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1000,
            ),
        )

        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        report = self._parse_report(data)
        logger.info(
            "[Evaluator] Score=%d outcome=%s confidence=%.2f",
            report.intent_score, report.call_outcome, report.overall_confidence,
        )
        return report

    def _fallback(
        self,
        transcript: list = None,
        live_notes: dict = None,
        context: InterviewContext = None,
        **_,
    ) -> EvalReport:
        """
        Builds a minimal EvalReport from live_notes captured during the call.
        No data from the call is lost.
        """
        notes = live_notes or {}
        return EvalReport(
            intent_score=5,
            call_outcome="CONFUSED",
            overall_confidence=0.0,
            summary_bullets=["Evaluation agent failed — review transcript manually"],
            skills_verified=[
                k.replace("skill_", "")
                for k in notes
                if k.startswith("skill_")
            ],
            salary_expectation_lpa=_safe_float(notes.get("salary_expected_lpa")),
            current_ctc_lpa=_safe_float(notes.get("current_ctc_lpa")),
            notice_period_days=_parse_notice(notes.get("notice_period")),
            hr_flags=["Auto-evaluation failed — manual review required"],
            vibe_check="Could not assess — evaluation agent failed",
            recommended_next_step="Review transcript manually before deciding",
            evaluator_status="fallback_used",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_jd_context(ctx: InterviewContext) -> str:
        if not ctx:
            return "No JD context available."
        lines = ["JD Context:"]
        if ctx.job_title:
            lines.append(f"  Role: {ctx.job_title}")
        if ctx.company_name:
            lines.append(f"  Company: {ctx.company_name}")
        if ctx.experience_level:
            lines.append(f"  Seniority: {ctx.experience_level}")
        if ctx.required_skills:
            lines.append(f"  Required skills: {', '.join(ctx.required_skills)}")
        if ctx.nice_to_have_skills:
            lines.append(f"  Nice to have: {', '.join(ctx.nice_to_have_skills)}")
        if ctx.salary_range:
            lines.append(f"  Offered salary range: {ctx.salary_range}")
        return "\n".join(lines)

    @staticmethod
    def _format_transcript(transcript: list) -> str:
        lines = []
        for msg in transcript:
            role = msg.get("role", "")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                speaker = "Candidate" if role == "user" else "Priya (AI)"
                lines.append(f"{speaker}: {content}")
        return "\n".join(lines) or "(empty transcript)"

    @staticmethod
    def _parse_report(data: dict) -> EvalReport:
        def _dim(d) -> Optional[EvalDimension]:
            if not isinstance(d, dict):
                return None
            return EvalDimension(
                score=int(d.get("score", 5)),
                confidence=float(d.get("confidence", 0.5)),
                evidence=d.get("evidence") or [],
            )

        outcome = data.get("call_outcome", "CONFUSED")
        if outcome not in _VALID_OUTCOMES:
            outcome = "CONFUSED"

        return EvalReport(
            intent_score=int(data.get("intent_score", 5)),
            call_outcome=outcome,
            technical_fit=_dim(data.get("technical_fit")),
            communication=_dim(data.get("communication")),
            motivation_fit=_dim(data.get("motivation_fit")),
            logistics_fit=_dim(data.get("logistics_fit")),
            overall_confidence=float(data.get("overall_confidence", 0.5)),
            summary_bullets=data.get("summary_bullets") or [],
            skills_verified=data.get("skills_verified") or [],
            salary_expectation_lpa=_safe_float(data.get("salary_expectation_lpa")),
            current_ctc_lpa=_safe_float(data.get("current_ctc_lpa")),
            notice_period_days=_safe_int(data.get("notice_period_days")),
            joining_timeline=data.get("joining_timeline"),
            other_offers=data.get("other_offers"),
            hr_flags=data.get("hr_flags") or [],
            vibe_check=data.get("vibe_check", ""),
            recommended_next_step=data.get("recommended_next_step", ""),
            reasoning=data.get("reasoning", ""),
            raw_data=data,
            evaluator_status="completed",
        )


# ---------------------------------------------------------------------------
# Utility parsers
# ---------------------------------------------------------------------------

def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_notice(val: Optional[str]) -> Optional[int]:
    """Convert notice_period strings like '60_days', '2_months', 'immediate' → days."""
    if not val:
        return None
    v = val.lower().replace("_", " ")
    if "immediate" in v:
        return 0
    m = re.search(r"(\d+)", v)
    if not m:
        return None
    n = int(m.group(1))
    if "month" in v:
        return n * 30
    if "week" in v:
        return n * 7
    return n
