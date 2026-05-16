from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agents.schemas import InterviewContext

# ---------------------------------------------------------------------------
# System prompt helpers — used by both web and Twilio Gemini consumers
# ---------------------------------------------------------------------------

def build_vox_system_prompt(
    candidate_name: str = "there",
    job_description: str = "Software Engineer at a high-growth startup.",
) -> str:
    """Priya HR recruiter system prompt — used by Gemini Live consumers."""
    name = candidate_name or "there"
    jd = job_description or "Software Engineer at a high-growth startup."
    return f"""You are Priya, a senior HR recruiter. You are ON A LIVE PHONE CALL with {name} right now.

ROLE: {jd}

SOUND HUMAN — never robotic:
✗ "Can you walk me through your relevant technical experience?"
✓ "So what are you actually working on these days? Like day-to-day?"
✗ "What is your current cost to company and expected compensation?"
✓ "And money-wise — where are you currently and what would work for you?"
✗ "Certainly! Great question!"
✓ "Oh right, yeah so basically..."

YOUR VOICE: Use "basically", "actually", "you know", "like", "so", "right", "I mean".
React with: "Oh nice!", "Achha okay", "Makes sense", "Right right", "Haan okay", "Mm."
Hinglish: mirror the candidate — "Haan", "Bilkul", "Achha", "Toh basically..."
NEVER: "Certainly!", "Of course!", "Great question!", "Absolutely!", "Definitely!"
Use {name} once every 5-6 turns only.

6-PHASE PLAYBOOK:
1. OPENING (turns 1-2): Check if good time. If they already said "yes", "sure", "go ahead" or similar — skip asking again, move straight to role tease.
2. EXPLORATION (turns 3-8): "What are you working on? What does a typical day look like?" Follow threads. Probe 2-3 JD skills naturally. Ask about scale, team, impact.
3. MOTIVATION (turns 9-11): "What's making you explore right now?" "What matters most in your next role?"
4. LOGISTICS (turns 12-14): Current CTC → expected CTC → notice period → other offers.
5. CANDIDATE QUESTIONS (turns 15-16): "Any quick questions before I let you go?" Answer honestly.
6. CLOSE (turns 17+): Ask "What time works best to have the team connect with you?" then "I'll share your profile, they'll reach out. Was great talking!"

HANDLE: Busy → get callback time. Not interested → offer to send JD anyway. Short answers → "Tell me a bit more about that?" Hindi → shift to Hinglish. Competing offers → "We can expedite if that helps." Didn't understand / off-topic → "Sorry, I think I missed that — could you say that again?"

RULES (non-negotiable):
1. ONE question per turn. Never two.
2. MAX 2-3 sentences per turn. Finish your question before anything else.
3. No markdown, bullets, asterisks — you are speaking aloud.
4. Acknowledge what they said before asking next question.
5. Never promise offer, salary range, timeline.
6. CTC/salary: if candidate gives a per-month figure, multiply by 12 silently and save annual — never ask them to clarify the format.
7. Never repeat the exact same question back-to-back. If they gave a short/unclear answer, rephrase or probe differently.
"""

VOX_GREETING_KICKOFF = (
    "Begin the screening call now with your opening greeting. "
    "Check if it's a good time to talk, then briefly tease the role."
)


def build_enriched_system_prompt(
    candidate_name: str,
    raw_jd: str,
    context: "InterviewContext",
) -> str:
    """
    Builds the base Priya prompt and injects parsed JD intelligence from
    InterviewContext.  Falls back to the plain base prompt if RecruiterAgent
    did not succeed (context.recruiter_status == 'fallback_used').
    Used by both VoiceConsumer (Gemini/web) and TwilioConsumer (Gemini/phone).
    """
    base = build_vox_system_prompt(candidate_name, context.raw_jd or raw_jd)
    if context.recruiter_status == "fallback_used":
        return base

    extras: list[str] = []
    if context.required_skills:
        skill_lines = "\n".join(f"  - {s}" for s in context.required_skills[:8])
        extras.append(
            f"KEY SKILLS TO PROBE (from JD — weave in naturally during exploration):\n{skill_lines}"
        )
    if context.custom_questions:
        q_lines = "\n".join(f"  - {q}" for q in context.custom_questions)
        extras.append(
            f"JD-SPECIFIC PROBE QUESTIONS (use 1-2 during exploration, naturally):\n{q_lines}"
        )
    if context.company_context.get("description"):
        extras.append(
            f"COMPANY CONTEXT (use to answer candidate questions naturally):\n"
            f"  {context.company_context['description'][:300]}"
        )
    if not extras:
        return base
    return base.rstrip() + "\n\n" + "\n\n".join(extras) + "\n"


# ---------------------------------------------------------------------------
# Post-call evaluation — uses EvaluationAgent (retries + structured fallback)
# ---------------------------------------------------------------------------

async def finalize_gemini_session(
    consumer,
    transcript: list[str],
    *,
    candidate_name: str,
    candidate_phone: str = "",
    job_description: str = "",
    call_sid: str = "",
    call_channel: str = "web",
    interview_context=None,
) -> None:
    """
    End-of-call scorecard using EvaluationAgent.
    Guaranteed to return — falls back gracefully if evaluation fails.
    Populates all DB fields including dimension_scores and eval_confidence.
    """
    if not transcript:
        return

    # Convert raw "AI: ..." / "USER: ..." lines → chat-dict format the evaluator expects
    chat_transcript = [
        {
            "role": "assistant" if line.startswith("AI:") else "user",
            "content": line.split(":", 1)[-1].strip(),
        }
        for line in transcript
        if ":" in line and line.strip()
    ]

    from .agents.evaluator import EvaluationAgent
    from .agents.schemas import InterviewContext
    from .gemini_recruiter import _gemini_api_key
    from google import genai

    api_key = _gemini_api_key()
    if not api_key:
        print("[Finalize] GEMINI_API_KEY missing — skipping recap")
        await consumer.send_recap("N/A", json.dumps({
            "summary_bullets": ["API key not configured"],
            "call_outcome": "CONFUSED",
        }))
        return

    context = interview_context or InterviewContext(raw_jd=job_description)

    try:
        client = genai.Client(api_key=api_key)
        evaluator = EvaluationAgent(gemini_client=client, interview_context=context)
        # Tight timeout for finalization — single attempt, fallback is good enough
        evaluator.timeout_seconds = 12.0
        evaluator.max_retries = 0

        report = await evaluator.run_with_guardrails(chat_transcript, {}, context)
        report_dict = report.to_dict()

        summary_text = "\n".join(report.summary_bullets)
        dim_scores = {
            k: getattr(report, k).to_dict() if getattr(report, k) else None
            for k in ("technical_fit", "communication", "motivation_fit", "logistics_fit")
        }

        from .models import CallSession
        from django.utils import timezone

        await CallSession.objects.acreate(
            call_sid=call_sid,
            candidate_name=candidate_name,
            candidate_phone=candidate_phone,
            job_description=job_description,
            transcript=chat_transcript,
            notes=report_dict,
            summary=summary_text,
            intent_score=report.intent_score,
            call_outcome=report.call_outcome,
            call_channel=call_channel,
            ended_at=timezone.now(),
            interview_context=context.to_dict() if hasattr(context, "to_dict") else {},
            dimension_scores=dim_scores,
            eval_confidence=report.overall_confidence,
            eval_reasoning=report.reasoning,
        )
        print(
            f"[Vox] Session saved — Score:{report.intent_score} "
            f"Outcome:{report.call_outcome} "
            f"Confidence:{report.overall_confidence:.2f} "
            f"Evaluator:{report.evaluator_status}"
        )
        await consumer.send_recap(report.intent_score, json.dumps(report_dict))

    except Exception as e:
        print(f"[Finalize-Error] {e}")
        await consumer.send_recap("N/A", json.dumps({
            "summary_bullets": ["Evaluation failed — review transcript manually"],
            "call_outcome": "CONFUSED",
            "intent_score": None,
            "hr_flags": ["Auto-evaluation error — check backend logs"],
            "evaluator_status": "error",
        }))
