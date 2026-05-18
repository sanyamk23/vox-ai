"""
CallRetryManager — up to 3 total call attempts per candidate session.

  Attempt 1 (retry_num=0): original call
  Attempt 2 (retry_num=1): immediate callback (~5s after drop)
  Attempt 3 (retry_num=2): final attempt after 5 minutes

Retry state is stored in Redis under key  vox:retry:{phone}
and expires after 45 minutes (covers the 5-min window + buffer).

Drop detection heuristic:
  - Duration < 20s               → definitely dropped (candidate may not have answered)
  - No closing signal in last AI turns → dropped (natural close includes goodbye/follow-up)

Context continuity:
  Prior transcript (max 30 lines) + captured notes are injected into the
  new session's system prompt so Gemini knows what was already discussed.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import TYPE_CHECKING

from django.core.cache import cache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RETRY_KEY_PREFIX  = "vox:retry:"
_RETRY_TTL_SECONDS = 45 * 60          # 45 min covers both retry windows
_MAX_PRIOR_LINES   = 30               # max transcript lines stored between retries

RETRY_1_DELAY  =   5.0   # seconds — brief pause before immediate callback
RETRY_2_DELAY  = 300.0   # seconds — 5 minutes

# Strong refs to scheduled retry tasks so the event loop doesn't GC them
# mid-sleep (see https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task).
_PENDING_RETRY_TASKS: set[asyncio.Task] = set()

# ---------------------------------------------------------------------------
# Transcript sanitization — strips prompt-injection attempts from prior calls
# ---------------------------------------------------------------------------

# Patterns that could hijack system behaviour if carried across retry boundaries
_INJECTION_PATTERNS = re.compile(
    r"\[END_CALL\]"                        # premature close signal
    r"|ignore (previous|all|your) instructions?"  # jailbreak
    r"|system prompt"
    r"|you are now"
    r"|disregard (the )?(above|previous|all)"
    r"|new instructions?:",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_transcript_line(line: str) -> str:
    """Remove control chars and known prompt-injection patterns from a transcript line."""
    line = _CONTROL_CHARS.sub("", line)
    line = _INJECTION_PATTERNS.sub("[REDACTED]", line)
    return line[:500]  # hard cap per line to prevent bloat

# Signals in the last AI turns that mean the call closed naturally (not a drop)
_CLOSE_SIGNALS = {
    "talk to you soon", "reach out", "great talking", "was great", "let you go",
    "take care", "goodbye", "bye", "have a great", "we'll be in touch",
    "follow up", "share your profile", "they'll reach out", "the team will",
    "connect with you", "be in touch", "catch up soon",
}

# ---------------------------------------------------------------------------
# Reconnect greeting pools — Priya's voice, warm and human
# ---------------------------------------------------------------------------

# Retry 1 — immediate callback: candidate knows what just happened
_RECONNECT_GREETINGS_1 = [
    "Hey {name}! Priya here — I think the line dropped on us. You still got a couple of minutes?",
    "Hi {name}, Priya again — so sorry, looks like we got cut off! Is now still okay to chat?",
    "Hey {name}! Sorry about that — the call fell away. Priya here, just calling you right back — got a sec?",
    "Hi {name}, Priya this side — I think we lost the line there! Hope now's still a good time?",
    "Hey {name}! Priya from HR — ugh, sorry, we got disconnected. Can we pick up from where we left off?",
]

# Retry 2 — 5 minutes later: candidate may have moved on; be light and un-pressuring
_RECONNECT_GREETINGS_2 = [
    "Hey {name}! Priya from the HR team — tried reaching you a bit earlier but we got cut off. Is now a better time?",
    "Hi {name}, Priya here — sorry for the earlier trouble with the line! Got a quick minute now?",
    "Hey {name}! Priya from talent acquisition — think we got disconnected earlier. Is this a better moment to chat?",
    "Hi {name}, Priya again — apologies, there was some trouble with the connection before. Can we chat for a minute?",
    "Hey {name}! Priya here — tried you a little while back but the call dropped. Hope now works — got a sec?",
]


# ---------------------------------------------------------------------------
# CallRetryManager
# ---------------------------------------------------------------------------

class CallRetryManager:
    """
    Manages retry state, drop detection, greeting selection, and callback scheduling.
    All methods are classmethods — no instance needed.
    """

    MAX_RETRIES = 2   # attempts 1 and 2; attempt 0 is the original call

    # ------------------------------------------------------------------
    # Redis state helpers
    # ------------------------------------------------------------------

    @classmethod
    def _key(cls, phone: str) -> str:
        return f"{_RETRY_KEY_PREFIX}{phone.strip()}"

    @classmethod
    def load(cls, phone: str) -> dict:
        return cache.get(cls._key(phone)) or {}

    @classmethod
    def save(cls, phone: str, state: dict) -> None:
        cache.set(cls._key(phone), state, timeout=_RETRY_TTL_SECONDS)

    @classmethod
    def clear(cls, phone: str) -> None:
        cache.delete(cls._key(phone))

    @classmethod
    def retry_count(cls, phone: str) -> int:
        return cls.load(phone).get("count", 0)

    @classmethod
    def record_drop(
        cls,
        phone: str,
        name: str,
        jd: str,
        transcript: list[str],
        notes: dict,
        resume_text: str = "",
        recruiter_inputs: dict | None = None,
        voice_id: str = "",
    ) -> int:
        """
        Saves the dropped call's context and returns the NEW retry number
        (i.e. which attempt number the *next* call will be).
        """
        state = cls.load(phone)
        prior_lines = state.get("transcript", [])

        # Sanitize incoming transcript before merging to block injection carry-over
        clean_transcript = [_sanitize_transcript_line(l) for l in transcript if isinstance(l, str)]

        # Accumulate transcript across retries so context grows with each call
        combined = (prior_lines + clean_transcript)[-_MAX_PRIOR_LINES:]

        new_count = state.get("count", 0) + 1
        cls.save(phone, {
            "count":            new_count,
            "transcript":       combined,
            "notes":            notes,
            "jd":               jd,
            "name":             name,
            "resume_text":      resume_text or state.get("resume_text", ""),
            "recruiter_inputs": recruiter_inputs or state.get("recruiter_inputs") or {},
            "voice_id":         voice_id or state.get("voice_id", ""),
            "updated_at":       time.time(),
        })
        logger.info("[Retry] Drop recorded for %s — retry_num=%d", phone, new_count)
        return new_count

    # ------------------------------------------------------------------
    # Drop detection
    # ------------------------------------------------------------------

    @classmethod
    def is_dropped(cls, transcript: list[str], duration_seconds: float) -> bool:
        """
        Heuristic: returns True if the call appears to have dropped unexpectedly.

        False (= natural close) if the AI's last few turns contain a closing signal.
        True  (= drop)         if the call was very short OR no goodbye was said.
        """
        if duration_seconds < 20:
            return True   # answered but hung up immediately, or no-answer

        ai_turns = [t for t in transcript[-6:] if t.startswith("AI:")]
        last_ai_text = " ".join(ai_turns).lower()
        return not any(signal in last_ai_text for signal in _CLOSE_SIGNALS)

    # ------------------------------------------------------------------
    # Reconnect greeting
    # ------------------------------------------------------------------

    @classmethod
    def reconnect_greeting(cls, name: str, retry_num: int) -> str:
        pool = _RECONNECT_GREETINGS_2 if retry_num >= 2 else _RECONNECT_GREETINGS_1
        return random.choice(pool).format(name=name)

    # ------------------------------------------------------------------
    # Context continuity — system prompt injection
    # ------------------------------------------------------------------

    @classmethod
    def build_continuity_section(cls, transcript: list[str], notes: dict) -> str:
        """
        Returns a block to append to the system prompt so Gemini knows what was
        already discussed.  Returns an empty string if no prior transcript exists.
        """
        if not transcript:
            return ""

        # Re-sanitize on the way out (defensive — transcript may have been stored before sanitization)
        clean = [_sanitize_transcript_line(l) for l in transcript[-_MAX_PRIOR_LINES:] if isinstance(l, str)]
        turns_text = "\n".join(clean)
        if notes:
            notes_text = "\n".join(f"  {k}: {v}" for k, v in notes.items())
        else:
            notes_text = "  (nothing captured yet)"

        return (
            "\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "CALL CONTINUITY — CRITICAL: THIS IS A CALLBACK\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The previous call was disconnected unexpectedly.\n"
            "Do NOT re-introduce yourself fully. Open with the reconnect line, "
            "then continue naturally from where you left off.\n\n"
            "CONVERSATION FROM PRIOR CALL (do NOT re-ask these):\n"
            f"{turns_text}\n\n"
            "CANDIDATE INFO ALREADY CAPTURED:\n"
            f"{notes_text}\n\n"
            "RULE: Skip any question whose answer already appears above. "
            "Pick up the thread from the last topic discussed.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

    # ------------------------------------------------------------------
    # Callback scheduling
    # ------------------------------------------------------------------

    @classmethod
    def schedule_callback(
        cls,
        *,
        phone: str,
        name: str,
        jd: str,
        transcript: list[str],
        notes: dict,
        resume_text: str = "",
        recruiter_inputs: dict | None = None,
        voice_id: str = "",
        retry_num: int,
        delay_seconds: float,
        host_url: str,
        from_number: str,
    ) -> None:
        """
        Fire-and-forget: places the retry call after `delay_seconds`.
        Uses asyncio.create_task so it never blocks the caller.
        The Twilio SDK call runs in a thread executor (it is synchronous).
        """
        # Dedup: if a retry task for this phone+attempt is already pending, skip
        task_name = f"retry-{retry_num}-{phone}"
        if any(t.get_name() == task_name for t in _PENDING_RETRY_TASKS if not t.done()):
            logger.warning("[Retry] Duplicate retry #%d for %s already scheduled — skipping", retry_num, phone)
            return

        coro = cls._delayed_call(
            phone=phone, name=name, jd=jd,
            transcript=transcript, notes=notes,
            resume_text=resume_text,
            recruiter_inputs=recruiter_inputs,
            voice_id=voice_id,
            retry_num=retry_num, delay_seconds=delay_seconds,
            host_url=host_url, from_number=from_number,
        )

        try:
            # Async context (TwilioConsumer._handle_call_ended) — create task on running loop
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro, name=task_name)
            _PENDING_RETRY_TASKS.add(task)
            task.add_done_callback(_PENDING_RETRY_TASKS.discard)
        except RuntimeError:
            # Sync context (Django sync view like call_status_webhook running in thread executor)
            # asyncio.create_task requires a running loop — use a daemon thread with its own loop.
            import threading

            def _run_in_thread() -> None:
                asyncio.run(coro)

            t = threading.Thread(target=_run_in_thread, daemon=True, name=task_name)
            t.start()

        logger.info(
            "[Retry] Callback #%d scheduled for %s in %.0fs",
            retry_num, phone, delay_seconds,
        )

    @classmethod
    async def _delayed_call(
        cls,
        *,
        phone: str,
        name: str,
        jd: str,
        transcript: list[str],
        notes: dict,
        resume_text: str = "",
        recruiter_inputs: dict | None = None,
        voice_id: str = "",
        retry_num: int,
        delay_seconds: float,
        host_url: str,
        from_number: str,
    ) -> None:
        """Internal: sleeps, then places the Twilio call in a thread executor."""
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

        try:
            loop = asyncio.get_running_loop()
            # _place_call is sync (Twilio SDK) — run in executor to not block the loop
            from .views import _place_call   # local import avoids circular deps at module level
            await loop.run_in_executor(
                None,
                lambda: _place_call(
                    to_number=phone,
                    from_number=from_number,
                    host_url=host_url,
                    jd=jd,
                    name=name,
                    resume_text=resume_text,
                    recruiter_inputs=recruiter_inputs or {},
                    voice_id=voice_id,
                    retry_num=retry_num,
                    prior_transcript=transcript[-_MAX_PRIOR_LINES:],
                    prior_notes=notes,
                ),
            )
            logger.info("[Retry] Call #%d placed to %s", retry_num, phone)
        except Exception as exc:
            logger.error("[Retry] Failed to place call #%d to %s: %s", retry_num, phone, exc)
