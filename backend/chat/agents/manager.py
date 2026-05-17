from __future__ import annotations

import asyncio
import logging
import os

from google import genai

from .recruiter import RecruiterAgent
from .evaluator import EvaluationAgent
from .summary_agent import SummaryAgent
from .schemas import CandidateSummary, InterviewContext, EvalReport

logger = logging.getLogger(__name__)

_OVERRIDE_FIELDS = [
    "company_overview", "team_details", "company_location",
    "years_of_experience", "ctc_range", "required_joining_timeline",
    "work_location_type",
]


def _apply_recruiter_overrides(context: InterviewContext, recruiter_inputs: dict) -> None:
    """Apply pre-filled structured fields from the UI, overriding AI-parsed values."""
    for field in _OVERRIDE_FIELDS:
        val = (recruiter_inputs.get(field) or "").strip()
        if val:
            setattr(context, field, val)


class AgentManager:
    """
    Session-scoped coordinator for all agents.

    Lifecycle:
      1. prepare_session()   — pre-call: RecruiterAgent parses JD → InterviewContext
      2. (call runs)         — Gemini Live handles the live conversation
      3. evaluate_session()  — post-call: EvaluationAgent scores transcript → EvalReport

    Guarantees:
      - prepare_session()  always returns an InterviewContext (fallback if agent fails)
      - evaluate_session() always returns an EvalReport        (fallback if agent fails)
      - Background intel fetch is fire-and-forget; failures are silently discarded
      - get_health_report() exposes the status of every agent run this session
    """

    def __init__(self, session_id: str = "default") -> None:
        self.session_id = session_id
        self._agents: dict[str, RecruiterAgent | EvaluationAgent] = {}
        self._gemini_client = self._init_gemini_client()

    # ------------------------------------------------------------------
    # Phase 1 — Pre-call
    # ------------------------------------------------------------------

    async def prepare_session(
        self,
        jd: str,
        candidate_name: str = "",
        recruiter_inputs: dict | None = None,
    ) -> InterviewContext:
        """
        Parse the JD and build an InterviewContext before the call starts.
        Guaranteed to return — falls back to raw-JD context if parsing fails.
        Also launches background company intel fetch (non-blocking).

        recruiter_inputs: pre-filled structured fields from the UI that override
        AI-parsed values (company_overview, team_details, company_location,
        years_of_experience, ctc_range, required_joining_timeline, work_location_type).
        """
        recruiter = RecruiterAgent(gemini_client=self._gemini_client)
        self._agents["recruiter"] = recruiter

        context: InterviewContext = await recruiter.run_with_guardrails(jd, candidate_name)
        self._log_agent("recruiter")

        if recruiter_inputs:
            _apply_recruiter_overrides(context, recruiter_inputs)

        # Launch background intel enrichment — does NOT block call start
        if context.company_name:
            asyncio.create_task(
                self._background_intel(recruiter, context),
                name=f"intel-{self.session_id}",
            )

        return context

    async def _background_intel(
        self,
        recruiter: RecruiterAgent,
        context: InterviewContext,
    ) -> None:
        """Fire-and-forget: enriches context.company_context in place. Never raises."""
        try:
            intel = await recruiter.fetch_background_intel(context.company_name)
            if intel:
                context.company_context.update(intel)
                logger.info(
                    "[Manager] Background intel ready for %r: %d chars",
                    context.company_name,
                    len(intel.get("description", "")),
                )
        except Exception as exc:
            logger.debug("[Manager] Background intel silently failed: %s", exc)

    # ------------------------------------------------------------------
    # Phase 3 — Post-call
    # ------------------------------------------------------------------

    async def evaluate_session(
        self,
        transcript: list,
        live_notes: dict,
        context: InterviewContext,
    ) -> EvalReport:
        """
        Score the candidate against the JD after the call ends.
        Guaranteed to return — falls back to EvalReport built from live_notes.
        """
        evaluator = EvaluationAgent(
            gemini_client=self._gemini_client,
            interview_context=context,
        )
        self._agents["evaluator"] = evaluator

        report: EvalReport = await evaluator.run_with_guardrails(transcript, live_notes, context)
        self._log_agent("evaluator")
        return report

    # ------------------------------------------------------------------
    # Phase 3b — Candidate summary (runs after evaluate_session)
    # ------------------------------------------------------------------

    async def summarize_candidate(
        self,
        context: InterviewContext,
        report: EvalReport,
        resume_text: str = "",
    ) -> CandidateSummary:
        """
        Evaluate candidate compatibility against recruiter requirements.
        Guaranteed to return — falls back to a yellow CandidateSummary if agent fails.
        """
        summarizer = SummaryAgent(gemini_client=self._gemini_client)
        self._agents["summary"] = summarizer

        summary: CandidateSummary = await summarizer.run_with_guardrails(
            context, report, resume_text
        )
        self._log_agent("summary")
        return summary

    # ------------------------------------------------------------------
    # Health & observability
    # ------------------------------------------------------------------

    def get_health_report(self) -> dict:
        return {
            "session_id": self.session_id,
            "agents": {
                name: agent.health_report()
                for name, agent in self._agents.items()
            },
        }

    def _log_agent(self, name: str) -> None:
        agent = self._agents.get(name)
        if agent:
            report = agent.health_report()
            level = logging.INFO if agent.is_healthy else logging.WARNING
            logger.log(level, "[Manager] %s", report)

    # ------------------------------------------------------------------
    # Gemini client (shared across all agents in this session)
    # ------------------------------------------------------------------

    def _init_gemini_client(self) -> genai.Client:
        api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        return genai.Client(api_key=api_key)
