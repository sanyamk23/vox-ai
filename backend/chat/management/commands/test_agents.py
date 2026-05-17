"""
Management command: test the multi-agent pipeline end-to-end.

Usage:
  python manage.py test_agents              # full suite
  python manage.py test_agents --only=recruiter
  python manage.py test_agents --only=evaluator
  python manage.py test_agents --only=manager
  python manage.py test_agents --only=guardrails
  python manage.py test_agents --verbose
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from django.core.management.base import BaseCommand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(label: str, detail: str = "") -> None:
    suffix = f"  {detail}" if detail else ""
    print(f"  \033[32m✓\033[0m  {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f"  {detail}" if detail else ""
    print(f"  \033[31m✗\033[0m  {label}{suffix}")


def _section(title: str) -> None:
    print(f"\n\033[1;34m{'─' * 55}\033[0m")
    print(f"\033[1;34m  {title}\033[0m")
    print(f"\033[1;34m{'─' * 55}\033[0m")


def _timed(label: str, elapsed: float) -> str:
    return f"({elapsed:.2f}s)"


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_JD = """
Senior Backend Engineer — Fintech (Series B, Mumbai/Remote)

We are looking for a senior engineer to own our payment processing infrastructure.

Requirements:
- 4+ years of Python (FastAPI / Django)
- Strong experience with PostgreSQL and Redis
- Kubernetes and AWS (EKS preferred)
- Experience with high-throughput systems (>10k TPS)
- Understanding of PCI-DSS compliance is a plus
- Strong system design skills

Nice to have:
- Kafka or RabbitMQ for async messaging
- Previous fintech or payments domain experience

Compensation: ₹35-50 LPA depending on experience
Location: Remote-first, optional Mumbai office access
""".strip()

SAMPLE_TRANSCRIPT = [
    {"role": "system", "content": "You are Priya..."},
    {"role": "assistant", "content": "Hi Rahul! This is Priya from HR. Got a minute?"},
    {"role": "user", "content": "Yeah sure, go ahead!"},
    {"role": "assistant", "content": "Great! So we have a Senior Backend Engineer role. What are you currently working on?"},
    {"role": "user", "content": "I'm at Razorpay currently, working on the payments API team. We handle about 15k TPS peak load."},
    {"role": "assistant", "content": "Oh nice, that's solid scale! What tech stack are you on there?"},
    {"role": "user", "content": "Mostly Python and FastAPI, PostgreSQL, Redis. We use Kubernetes on AWS."},
    {"role": "assistant", "content": "Perfect match. What's making you explore right now?"},
    {"role": "user", "content": "Honestly just looking for something with more ownership. Razorpay is great but I want to build things from scratch."},
    {"role": "assistant", "content": "That makes sense. Money-wise, where are you currently and what would work?"},
    {"role": "user", "content": "Currently at 28 LPA. Looking for something around 40-42."},
    {"role": "assistant", "content": "Got it. And notice period?"},
    {"role": "user", "content": "60 days but I might be able to negotiate it down."},
    {"role": "assistant", "content": "Sounds good. Any other offers you're considering?"},
    {"role": "user", "content": "I have one from a US startup but it's early stage so not sure yet."},
    {"role": "assistant", "content": "Okay. Any questions for me before I let you go?"},
    {"role": "user", "content": "What's the team size and how's the engineering culture?"},
    {"role": "assistant", "content": "Engineering team is around 20, very autonomous, async-first. I'll have the team reach out to connect!"},
    {"role": "user", "content": "Sounds great, looking forward to it."},
]

SAMPLE_LIVE_NOTES = {
    "current_ctc_lpa": "28",
    "salary_expected_lpa": "42",
    "notice_period": "60_days",
    "skill_python": "confirmed",
    "skill_fastapi": "confirmed",
    "skill_postgresql": "confirmed",
    "skill_kubernetes": "confirmed",
    "current_company": "Razorpay",
    "current_role": "Backend Engineer",
    "total_experience_years": "5",
    "has_competing_offers": "yes",
}


# ---------------------------------------------------------------------------
# Individual test suites
# ---------------------------------------------------------------------------

async def test_recruiter(verbose: bool) -> dict[str, Any]:
    from chat.agents.recruiter import RecruiterAgent
    from chat.agents.schemas import InterviewContext
    from google import genai

    results: dict[str, Any] = {"passed": 0, "failed": 0}
    _section("RecruiterAgent")

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not gemini_key:
        _fail("GEMINI_API_KEY not set — skipping live tests")
        return results

    gemini = genai.Client(api_key=gemini_key)

    # --- Test 1: Real JD parsing ---
    t0 = time.perf_counter()
    agent = RecruiterAgent(gemini_client=gemini)
    ctx: InterviewContext = await agent.run_with_guardrails(SAMPLE_JD, "Rahul")
    elapsed = time.perf_counter() - t0

    if ctx.recruiter_status == "completed":
        _ok("JD parsing succeeded", _timed("", elapsed))
        results["parsed_context"] = ctx
    else:
        _fail("JD parsing fell back (check Gemini key / connectivity)", _timed("", elapsed))
        results["failed"] += 1

    if verbose and ctx.recruiter_status == "completed":
        print(f"       job_title       : {ctx.job_title}")
        print(f"       company_name    : {ctx.company_name}")
        print(f"       experience_level: {ctx.experience_level}")
        print(f"       domain          : {ctx.domain}")
        print(f"       required_skills : {ctx.required_skills}")
        print(f"       custom_questions:")
        for q in ctx.custom_questions:
            print(f"         - {q}")
        print(f"       phase_weights   : {ctx.phase_weights}")

    assert_cases = [
        ("job_title not empty", bool(ctx.job_title)),
        ("required_skills list", isinstance(ctx.required_skills, list)),
        ("custom_questions ≤ 3", len(ctx.custom_questions) <= 3),
        ("experience_level valid", ctx.experience_level in {"junior","mid","senior","lead","principal","fallback_used"}),
        ("raw_jd preserved", bool(ctx.raw_jd)),
    ]
    for label, condition in assert_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    # --- Test 2: Fallback on empty JD ---
    agent2 = RecruiterAgent(gemini_client=gemini)
    ctx2 = await agent2.run_with_guardrails("hi", "Test")
    if ctx2.recruiter_status == "fallback_used":
        _ok("Empty JD triggers immediate fallback (no LLM call)")
        results["passed"] += 1
    else:
        _fail("Empty JD should have triggered fallback")
        results["failed"] += 1

    # --- Test 3: Health report ---
    report = agent.health_report()
    if report.get("agent") == "recruiter" and report.get("status") in (
        "completed", "fallback_used"
    ):
        _ok("health_report() returns correct shape")
        results["passed"] += 1
    else:
        _fail("health_report() malformed", str(report))
        results["failed"] += 1

    # --- Test 4: Background intel (fire-and-forget, should not raise) ---
    try:
        intel = await agent.fetch_background_intel("Razorpay")
        _ok("Background intel fetch did not raise", f"keys={list(intel.keys())}")
        results["passed"] += 1
    except Exception as e:
        _fail(f"Background intel raised unexpectedly: {e}")
        results["failed"] += 1

    return results


async def test_evaluator(verbose: bool) -> dict[str, Any]:
    from chat.agents.evaluator import EvaluationAgent
    from chat.agents.schemas import InterviewContext, EvalReport
    from google import genai

    results: dict[str, Any] = {"passed": 0, "failed": 0}
    _section("EvaluationAgent")

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not gemini_key:
        _fail("GEMINI_API_KEY not set — skipping live tests")
        return results

    gemini = genai.Client(api_key=gemini_key)
    context = InterviewContext(
        job_title="Senior Backend Engineer",
        company_name="Fintech Startup",
        required_skills=["Python", "PostgreSQL", "Redis", "Kubernetes"],
        experience_level="senior",
        domain="fintech",
        raw_jd=SAMPLE_JD,
        recruiter_status="completed",
    )

    # --- Test 1: Real evaluation ---
    t0 = time.perf_counter()
    agent = EvaluationAgent(gemini_client=gemini, interview_context=context)
    report: EvalReport = await agent.run_with_guardrails(
        SAMPLE_TRANSCRIPT, SAMPLE_LIVE_NOTES, context
    )
    elapsed = time.perf_counter() - t0

    if report.evaluator_status == "completed":
        _ok("Evaluation succeeded", _timed("", elapsed))
    else:
        _fail("Evaluation fell back", _timed("", elapsed))
        results["failed"] += 1

    if verbose:
        print(f"       intent_score    : {report.intent_score}")
        print(f"       call_outcome    : {report.call_outcome}")
        print(f"       overall_conf    : {report.overall_confidence:.2f}")
        print(f"       technical_fit   : {report.technical_fit.score if report.technical_fit else 'N/A'}")
        print(f"       communication   : {report.communication.score if report.communication else 'N/A'}")
        print(f"       motivation_fit  : {report.motivation_fit.score if report.motivation_fit else 'N/A'}")
        print(f"       logistics_fit   : {report.logistics_fit.score if report.logistics_fit else 'N/A'}")
        print(f"       skills_verified : {report.skills_verified}")
        print(f"       hr_flags        : {report.hr_flags}")
        print(f"       vibe_check      : {report.vibe_check}")
        print(f"       reasoning       : {report.reasoning[:120]}...")

    assert_cases = [
        ("intent_score 1-10", 1 <= report.intent_score <= 10),
        ("call_outcome valid", report.call_outcome in {
            "INTERESTED","BUSY","NOT_INTERESTED","CALLBACK_REQUESTED","CONFUSED"
        }),
        ("overall_confidence 0-1", 0.0 <= report.overall_confidence <= 1.0),
        ("to_dict() returns dict", isinstance(report.to_dict(), dict)),
        ("vibe_check not empty", bool(report.vibe_check)),
        ("recommended_next_step set", bool(report.recommended_next_step)),
    ]
    for label, condition in assert_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    # --- Test 2: Fallback from live_notes ---
    bad_agent = EvaluationAgent(gemini_client=gemini)
    fallback = bad_agent._fallback(
        transcript=[], live_notes=SAMPLE_LIVE_NOTES, context=context
    )
    fallback_cases = [
        ("fallback status = fallback_used", fallback.evaluator_status == "fallback_used"),
        ("fallback extracts salary", fallback.salary_expectation_lpa == 42.0),
        ("fallback extracts notice (60_days → 60)", fallback.notice_period_days == 60),
        ("fallback extracts skills", len(fallback.skills_verified) > 0),
        ("fallback confidence = 0.0", fallback.overall_confidence == 0.0),
        ("fallback hr_flags set", len(fallback.hr_flags) > 0),
    ]
    for label, condition in fallback_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label, "(check fallback logic)")
            results["failed"] += 1

    return results


async def test_manager(verbose: bool) -> dict[str, Any]:
    from chat.agents.manager import AgentManager

    results: dict[str, Any] = {"passed": 0, "failed": 0}
    _section("AgentManager (end-to-end)")

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        _fail("GEMINI_API_KEY not set — skipping")
        return results

    manager = AgentManager(session_id="test-session-001")

    # --- Phase 1: prepare_session ---
    t0 = time.perf_counter()
    context = await manager.prepare_session(jd=SAMPLE_JD, candidate_name="Rahul")
    elapsed = time.perf_counter() - t0

    prep_cases = [
        ("prepare_session returns InterviewContext", hasattr(context, "raw_jd")),
        ("recruiter ran", "recruiter" in manager._agents),
        ("recruiter is_healthy", manager._agents["recruiter"].is_healthy),
        ("context.raw_jd preserved", bool(context.raw_jd)),
    ]
    for label, condition in prep_cases:
        if condition:
            _ok(label, _timed("", elapsed) if "prepare" in label else "")
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    if verbose:
        print(f"       recruiter health : {manager._agents['recruiter'].health_report()}")
        print(f"       company_name     : {context.company_name}")
        print(f"       skills           : {context.required_skills[:4]}")

    # --- Phase 3: evaluate_session ---
    t0 = time.perf_counter()
    report = await manager.evaluate_session(
        transcript=SAMPLE_TRANSCRIPT,
        live_notes=SAMPLE_LIVE_NOTES,
        context=context,
    )
    elapsed = time.perf_counter() - t0

    eval_cases = [
        ("evaluate_session returns EvalReport", hasattr(report, "intent_score")),
        ("evaluator ran", "evaluator" in manager._agents),
        ("evaluator is_healthy", manager._agents["evaluator"].is_healthy),
        ("score is integer", isinstance(report.intent_score, int)),
    ]
    for label, condition in eval_cases:
        if condition:
            _ok(label, _timed("", elapsed) if "evaluate" in label else "")
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    # --- Health report ---
    health = manager.get_health_report()
    if health.get("session_id") == "test-session-001" and "agents" in health:
        _ok("get_health_report() correct shape")
        results["passed"] += 1
    else:
        _fail("get_health_report() malformed", str(health))
        results["failed"] += 1

    if verbose:
        print(f"\n       Full health report:")
        for name, info in health["agents"].items():
            print(f"         {name}: status={info['status']} attempts={info['attempts']}")
        print(f"\n       Final EvalReport:")
        print(f"         intent_score   = {report.intent_score}")
        print(f"         call_outcome   = {report.call_outcome}")
        print(f"         evaluator_status = {report.evaluator_status}")
        if report.technical_fit:
            print(f"         technical_fit  = {report.technical_fit.score} (conf={report.technical_fit.confidence:.2f})")
        print(f"         salary_expect  = {report.salary_expectation_lpa} LPA")
        print(f"         notice_period  = {report.notice_period_days} days")

    return results


async def test_guardrails(verbose: bool) -> dict[str, Any]:
    """Tests BaseAgent timeout and retry behaviour without hitting real APIs."""
    from chat.agents.base import BaseAgent, AgentStatus

    results: dict[str, Any] = {"passed": 0, "failed": 0}
    _section("Guardrails (timeout / retry / fallback)")

    # --- Agent that always times out ---
    class SlowAgent(BaseAgent):
        name = "slow-test"
        timeout_seconds = 0.1   # 100ms — will always time out
        max_retries = 1

        async def _execute(self, *args, **kwargs):
            await asyncio.sleep(10)   # much longer than timeout

        def _fallback(self, *args, **kwargs):
            return "fallback-value"

    agent = SlowAgent()
    t0 = time.perf_counter()
    result = await agent.run_with_guardrails()
    elapsed = time.perf_counter() - t0

    timeout_cases = [
        ("Timeout triggers fallback", result == "fallback-value"),
        ("Status is timed_out or fallback_used", agent.status in (
            AgentStatus.TIMED_OUT, AgentStatus.FALLBACK_USED
        )),
        ("Tried max_retries + 1 times", agent._attempt == 2),
        ("Elapsed ≈ 2× timeout (0.1s × 2 attempts)", elapsed < 1.0),
    ]
    for label, condition in timeout_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label, f"result={result!r} status={agent.status} elapsed={elapsed:.2f}s")
            results["failed"] += 1

    # --- Agent that fails with exception ---
    class FailingAgent(BaseAgent):
        name = "failing-test"
        timeout_seconds = 5.0
        max_retries = 2

        async def _execute(self, *args, **kwargs):
            raise ValueError("Deliberate test failure")

        def _fallback(self, *args, **kwargs):
            return "safe-fallback"

    agent2 = FailingAgent()
    result2 = await agent2.run_with_guardrails()

    fail_cases = [
        ("Exception triggers fallback", result2 == "safe-fallback"),
        ("Status is failed or fallback_used", agent2.status in (
            AgentStatus.FAILED, AgentStatus.FALLBACK_USED
        )),
        ("Tried max_retries + 1 times", agent2._attempt == 3),
        ("Error captured in health report", agent2.health_report()["error"] is not None),
    ]
    for label, condition in fail_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label, f"result={result2!r} status={agent2.status}")
            results["failed"] += 1

    # --- Agent that succeeds on 2nd retry ---
    class FlakyAgent(BaseAgent):
        name = "flaky-test"
        timeout_seconds = 5.0
        max_retries = 2

        def __init__(self):
            super().__init__()
            self._calls = 0

        async def _execute(self, *args, **kwargs):
            self._calls += 1
            if self._calls < 2:
                raise RuntimeError("First call fails")
            return "success-on-retry"

        def _fallback(self, *args, **kwargs):
            return "fallback"

    agent3 = FlakyAgent()
    result3 = await agent3.run_with_guardrails()

    retry_cases = [
        ("Succeeds on retry", result3 == "success-on-retry"),
        ("Status is completed", agent3.status == AgentStatus.COMPLETED),
        ("Took 2 attempts", agent3._attempt == 2),
    ]
    for label, condition in retry_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label, f"result={result3!r} status={agent3.status}")
            results["failed"] += 1

    if verbose:
        print(f"\n       SlowAgent health  : {SlowAgent().health_report()}")

    return results


async def test_retry(verbose: bool) -> dict[str, Any]:
    """Tests CallRetryManager: drop detection, greeting selection, continuity prompt."""
    from chat.retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY

    results: dict[str, Any] = {"passed": 0, "failed": 0}
    _section("CallRetryManager (drop detection / context continuity)")

    # Use a fake phone number so we don't touch production Redis keys
    TEST_PHONE = "+910000000001"

    # Ensure clean state
    CallRetryManager.clear(TEST_PHONE)

    # --- Test 1: Drop detection — short call ---
    dropped_short = CallRetryManager.is_dropped([], duration_seconds=8.0)
    if dropped_short:
        _ok("Short call (8s, no transcript) → detected as dropped")
        results["passed"] += 1
    else:
        _fail("Short call should be detected as dropped")
        results["failed"] += 1

    # --- Test 2: Drop detection — no closing signal ---
    mid_transcript = [
        "AI: Hey Rahul! Priya here — got a quick minute?",
        "USER: Yeah sure.",
        "AI: Great! So we have a Senior Backend role. What are you working on?",
        "USER: I'm at Razorpay, working on payments.",
    ]
    dropped_mid = CallRetryManager.is_dropped(mid_transcript, duration_seconds=45.0)
    if dropped_mid:
        _ok("Mid-conversation drop (no closing signal) → detected as dropped")
        results["passed"] += 1
    else:
        _fail("Mid-conversation drop should be detected")
        results["failed"] += 1

    # --- Test 3: Natural close NOT detected as drop ---
    close_transcript = [
        "AI: Great talking with you Rahul!",
        "USER: Thanks, looking forward to it.",
        "AI: I'll share your profile, the team will reach out. Take care, bye!",
    ]
    dropped_close = CallRetryManager.is_dropped(close_transcript, duration_seconds=300.0)
    if not dropped_close:
        _ok("Natural close (goodbye signal present) → NOT detected as dropped")
        results["passed"] += 1
    else:
        _fail("Natural close should NOT be detected as dropped")
        results["failed"] += 1

    # --- Test 4: record_drop accumulates transcript ---
    count1 = CallRetryManager.record_drop(
        phone=TEST_PHONE, name="Rahul", jd="SWE role",
        transcript=mid_transcript, notes={"current_ctc_lpa": "28"},
    )
    if count1 == 1:
        _ok("record_drop() returns retry_num=1 on first drop")
        results["passed"] += 1
    else:
        _fail(f"Expected retry_num=1, got {count1}")
        results["failed"] += 1

    state = CallRetryManager.load(TEST_PHONE)
    if state.get("count") == 1 and len(state.get("transcript", [])) == len(mid_transcript):
        _ok("Retry state saved in Redis with correct transcript")
        results["passed"] += 1
    else:
        _fail("Redis state mismatch", str(state))
        results["failed"] += 1

    # --- Test 5: Second drop accumulates (count becomes 2) ---
    more_transcript = ["USER: Hello?", "AI: Hi, can you hear me?"]
    count2 = CallRetryManager.record_drop(
        phone=TEST_PHONE, name="Rahul", jd="SWE role",
        transcript=more_transcript, notes={},
    )
    state2 = CallRetryManager.load(TEST_PHONE)
    combined_len = len(mid_transcript) + len(more_transcript)
    if count2 == 2 and len(state2.get("transcript", [])) == combined_len:
        _ok("Second drop accumulates transcript (count=2)")
        results["passed"] += 1
    else:
        _fail(f"Expected count=2 / len={combined_len}, got count={count2} / len={len(state2.get('transcript',[]))}")
        results["failed"] += 1

    # --- Test 6: Greeting selection ---
    g1 = CallRetryManager.reconnect_greeting("Rahul", retry_num=1)
    g2 = CallRetryManager.reconnect_greeting("Rahul", retry_num=2)
    greet_cases = [
        ("Retry 1 greeting contains 'Rahul'", "Rahul" in g1),
        ("Retry 2 greeting contains 'Rahul'", "Rahul" in g2),
        ("Retry 1 and 2 greetings are different", g1 != g2),
    ]
    for label, condition in greet_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label, f"g1={g1!r} g2={g2!r}")
            results["failed"] += 1

    # --- Test 7: Continuity section injected into system prompt ---
    prior = mid_transcript[:3]
    section = CallRetryManager.build_continuity_section(
        prior, {"current_ctc_lpa": "28", "notice_period": "60_days"}
    )
    continuity_cases = [
        ("Continuity section is non-empty", bool(section)),
        ("Contains 'CALLBACK' keyword", "CALLBACK" in section),
        ("Contains prior transcript lines", "Razorpay" in section or "USER:" in section),
        ("Contains captured notes", "current_ctc_lpa" in section),
    ]
    for label, condition in continuity_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    # --- Test 8: Clear removes state ---
    CallRetryManager.clear(TEST_PHONE)
    cleared = CallRetryManager.load(TEST_PHONE)
    if not cleared:
        _ok("clear() removes retry state from Redis")
        results["passed"] += 1
    else:
        _fail("clear() did not remove state", str(cleared))
        results["failed"] += 1

    # --- Test 9: Delay constants are correct ---
    delay_cases = [
        ("RETRY_1_DELAY ≥ 5s and ≤ 30s", 5 <= RETRY_1_DELAY <= 30),
        ("RETRY_2_DELAY == 300s (5 min)", RETRY_2_DELAY == 300.0),
    ]
    for label, condition in delay_cases:
        if condition:
            _ok(label)
            results["passed"] += 1
        else:
            _fail(label)
            results["failed"] += 1

    if verbose:
        print(f"\n       Retry 1 greeting : {g1}")
        print(f"       Retry 2 greeting : {g2}")
        print(f"\n       Continuity section preview:")
        for line in section.split("\n")[:12]:
            print(f"         {line}")

    return results


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Run end-to-end tests for the multi-agent pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=["recruiter", "evaluator", "manager", "guardrails", "retry"],
            help="Run only one test suite",
        )
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Print detailed field values",
        )

    def handle(self, *args, **options):
        only   = options.get("only")
        verbose = options.get("verbose", False)

        print("\n\033[1;33m  Vox AI — Agent Pipeline Test Suite\033[0m")
        print(f"  GEMINI_API_KEY : {'set' if os.getenv('GEMINI_API_KEY') else 'NOT SET'}")

        suites = {
            "guardrails": test_guardrails,
            "retry":      test_retry,
            "recruiter":  test_recruiter,
            "evaluator":  test_evaluator,
            "manager":    test_manager,
        }

        if only:
            suites = {only: suites[only]}

        total_passed = total_failed = 0

        async def run_all():
            nonlocal total_passed, total_failed
            for name, fn in suites.items():
                try:
                    result = await fn(verbose)
                    total_passed += result.get("passed", 0)
                    total_failed += result.get("failed", 0)
                except Exception as exc:
                    print(f"\n\033[31m  SUITE CRASHED ({name}): {exc}\033[0m")
                    import traceback
                    traceback.print_exc()
                    total_failed += 1

        asyncio.run(run_all())

        print(f"\n{'─' * 55}")
        color = "\033[32m" if total_failed == 0 else "\033[31m"
        print(
            f"{color}  Result: {total_passed} passed, "
            f"{total_failed} failed\033[0m\n"
        )

        if total_failed > 0:
            raise SystemExit(1)
