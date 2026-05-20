from __future__ import annotations

import logging
import os

from google import genai
from google.genai import types

from .base import BaseAgent
from .schemas import CandidateSummary, EvalReport, InterviewContext

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.0-flash")

_SUMMARY_SYSTEM = """\
You are a strict talent acquisition analyst. Evaluate candidate compatibility against role requirements.

Return ONLY valid JSON — no markdown fences, no extra text:
{
  "compatibility_level": "<green|yellow|red>",
  "compatibility_reason": "<One clear sentence explaining WHY this level was assigned>",
  "summary_bullets": ["<3-5 concise bullets describing the candidate for quick recruiter review>"],
  "match_points": ["<Specific things the candidate has that match the role requirements>"],
  "gap_points": ["<Specific things that are missing, mismatched, or concerning>"],
  "missing_skills": ["<Required skills not evidenced in resume or call — use exact skill names from JD>"],
  "red_flags": ["<Hard blockers: salary gap, notice mismatch, experience shortfall, location conflict>"],
  "recommendation": "<shortlist|hold|reject>",
  "recommendation_reason": "<One sentence explaining the recommendation>"
}

COMPATIBILITY LEVELS (apply strictly):
- GREEN  : Candidate meets 80%+ of requirements with no hard blockers → ready to shortlist
- YELLOW : Candidate meets 50–79% of requirements, OR has 1-2 significant but negotiable gaps
- RED    : Candidate meets <50% of requirements, OR has at least one hard blocker

HARD BLOCKERS (any one alone forces RED):
- Actual experience < 60% of required (e.g. 2 yrs actual vs 5 yrs required)
- A critical required skill is completely absent from resume AND call
- Candidate CTC expectation is >25% above offered range AND signalled as non-negotiable
- Notice period is >2x the required joining timeline AND candidate was inflexible
- Location / work-mode mismatch AND candidate was unwilling to accommodate

STRICT EVALUATION RULES:
- Base every point on evidence: resume text, skills verified on call, logistics captured
- Be specific in gaps: write "missing FastAPI" not "has technical gaps"
- If a required field was never discussed, mark it as "not verified — assume risk" in gap_points
- missing_skills must only list skills that appear in the JD requirements
- gap_points should include logistics mismatches (CTC, notice, location) when they exist
- Do not speculate or give benefit of the doubt on hard blockers
"""


def _build_evaluation_prompt(
    context: InterviewContext,
    report: EvalReport,
    resume_text: str,
) -> str:
    lines: list[str] = ["=== ROLE REQUIREMENTS ==="]
    lines.append(f"Job Title       : {context.job_title}")
    if context.required_skills:
        lines.append(f"Required Skills : {', '.join(context.required_skills)}")
    if context.nice_to_have_skills:
        lines.append(f"Nice to Have    : {', '.join(context.nice_to_have_skills)}")
    if context.years_of_experience:
        lines.append(f"Experience      : {context.years_of_experience}")
    lines.append(f"Level           : {context.experience_level}")
    if context.domain:
        lines.append(f"Domain          : {context.domain}")
    if context.ctc_range:
        lines.append(f"Offered CTC     : {context.ctc_range}")
    if context.required_joining_timeline:
        lines.append(f"Joining By      : {context.required_joining_timeline}")
    if context.work_location_type:
        lines.append(f"Work Mode       : {context.work_location_type}")
    if context.company_location:
        lines.append(f"Location        : {context.company_location}")
    if context.team_details:
        lines.append(f"Team            : {context.team_details}")

    lines.append("\n=== CANDIDATE PROFILE ===")

    if resume_text and resume_text.strip():
        snippet = resume_text.strip()[:3000]
        lines.append(f"[Resume]\n{snippet}")
    else:
        lines.append("[Resume] Not provided")

    lines.append("\n[Call Intelligence]")
    if report.skills_verified:
        lines.append(f"Skills Verified : {', '.join(report.skills_verified)}")
    else:
        lines.append("Skills Verified : None confirmed on call")

    # Logistics
    if report.salary_expectation_lpa is not None:
        lines.append(f"Expected CTC    : {report.salary_expectation_lpa} LPA")
    if report.current_ctc_lpa is not None:
        lines.append(f"Current CTC     : {report.current_ctc_lpa} LPA")
    if report.notice_period_days is not None:
        lines.append(f"Notice Period   : {report.notice_period_days} days")
    if report.joining_timeline:
        lines.append(f"Joining (said)  : {report.joining_timeline}")
    if report.other_offers is not None:
        lines.append(f"Other Offers    : {'Yes' if report.other_offers else 'No'}")

    # Dimension scores
    lines.append("\n[Dimension Scores]")
    for dim_key in ("technical_fit", "communication", "motivation_fit", "logistics_fit"):
        dim = getattr(report, dim_key, None)
        if dim:
            lines.append(f"  {dim_key.replace('_', ' ').title()}: {dim.score}/10 (confidence {dim.confidence:.0%})")

    # HR flags from evaluator
    if report.hr_flags:
        lines.append(f"\n[Evaluator HR Flags]\n" + "\n".join(f"  - {f}" for f in report.hr_flags))

    return "\n".join(lines)


class SummaryAgent(BaseAgent):
    """
    Post-call candidate compatibility evaluator.
    Compares the candidate profile (resume + call transcript intelligence)
    against recruiter-defined requirements from InterviewContext.
    Returns a CandidateSummary with green / yellow / red compatibility level.
    """

    name = "summary"
    timeout_seconds = 10.0
    max_retries = 1

    def __init__(self, gemini_client: genai.Client) -> None:
        super().__init__()
        self.gemini = gemini_client

    async def _execute(
        self,
        context: InterviewContext,
        report: EvalReport,
        resume_text: str = "",
    ) -> CandidateSummary:
        prompt = (
            f"{_SUMMARY_SYSTEM}\n\n"
            f"{_build_evaluation_prompt(context, report, resume_text)}\n\n"
            "Now evaluate the candidate and return the JSON:"
        )

        resp = await self.gemini.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                # gemini-2.5-flash thinking burns through the output-token budget
                # before producing real JSON; disable it for structured-output calls.
                max_output_tokens=2048,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        from .evaluator import _parse_llm_json
        data = _parse_llm_json(resp.text or "")

        level = data.get("compatibility_level", "yellow").lower()
        if level not in ("green", "yellow", "red"):
            level = "yellow"

        summary = CandidateSummary(
            compatibility_level=level,
            compatibility_reason=data.get("compatibility_reason", ""),
            summary_bullets=(data.get("summary_bullets") or [])[:5],
            match_points=(data.get("match_points") or [])[:8],
            gap_points=(data.get("gap_points") or [])[:8],
            missing_skills=(data.get("missing_skills") or [])[:10],
            red_flags=(data.get("red_flags") or [])[:5],
            recommendation=data.get("recommendation", "hold"),
            recommendation_reason=data.get("recommendation_reason", ""),
            summary_status="completed",
        )
        logger.info(
            "[Summary] %s → %s (%s)",
            context.job_title,
            summary.compatibility_level.upper(),
            summary.recommendation,
        )
        return summary

    def _fallback(self, *args, **kwargs) -> CandidateSummary:
        return CandidateSummary(
            compatibility_level="yellow",
            compatibility_reason="Automated summary unavailable — review manually.",
            summary_status="fallback_used",
        )
