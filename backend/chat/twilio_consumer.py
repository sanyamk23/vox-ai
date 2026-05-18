import asyncio
import json
import logging
import os
import re
from urllib.parse import parse_qs, unquote

from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from asgiref.sync import sync_to_async

from .agent import (
    DEFAULT_VOICE_ID,
    VOICE_PROFILES,
    build_enriched_system_prompt,
    VOX_GREETING_KICKOFF,
    build_vox_greeting_kickoff,
)
from .agents.manager import AgentManager
from .agents.schemas import InterviewContext
from .gemini_recruiter import (
    GeminiLiveBridge,
    RECRUITER_PROMPT,
    SARAH_GREETING_KICKOFF,
)
from .retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY

logger = logging.getLogger(__name__)

_DEFAULT_JD = "Software Engineer at a high-growth startup."
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TwilioConsumer(AsyncWebsocketConsumer):
    """
    Twilio Media Stream WebSocket — Gemini Live (Priya recruiter).

    Retry flow:
      - On unexpected drop: retry up to CallRetryManager.MAX_RETRIES more times.
      - Retry 1: immediate callback (~10s), opens with warm reconnect line.
      - Retry 2: 5-minute callback, light un-pressuring tone.
      - Context continuity: prior transcript + captured notes are injected
        into the system prompt so Priya never re-asks answered questions.
    """

    async def connect(self):
        try:
            # ── Token from URL path (Twilio strips query params; path is always preserved) ──
            token = self.scope.get("url_route", {}).get("kwargs", {}).get("token", "").strip()
            logger.info("[Twilio] connect token=%s", token[:8] if token else "<none>")

            session: dict = {}
            if token:
                session = await sync_to_async(cache.get)(f"vox:{token}") or {}
                logger.info("[Twilio] cache token=%s session_keys=%s", token, list(session.keys()) if isinstance(session, dict) else type(session).__name__)
                if not session:
                    # Redis miss — recover session_data from DB (handles Redis restart/eviction)
                    try:
                        from .models import CallSession
                        db_row = await sync_to_async(
                            lambda: CallSession.objects.filter(session_token=token).first()
                        )()
                        if db_row and db_row.session_data:
                            session = dict(db_row.session_data)
                            # resume_text is not in session_data (stripped to avoid double PII storage)
                            # — restore it from the dedicated column.
                            if db_row.resume_text and "resume_text" not in session:
                                session["resume_text"] = db_row.resume_text
                            logger.info(
                                "[Twilio] Redis miss — recovered session from DB for token=%s",
                                token[:12],
                            )
                    except Exception as _db_exc:
                        logger.error("[Twilio] DB fallback failed: %s", _db_exc)

                if not session:
                    logger.warning("[Twilio] Invalid/expired token=%s — rejecting", token[:12])
                    await self.accept()
                    await self.close(code=4401)
                    return
            else:
                logger.warning("[Twilio] No token in URL path — rejecting WebSocket")
                await self.accept()
                await self.close(code=4401)
                return

            await self.accept()
            logger.info("[Twilio] Socket accepted for token=%s", token[:8])

            # ── Sanitize string fields from session ───────────────────────────
            def _clean(s: str, max_len: int = 200) -> str:
                return _CONTROL_RE.sub("", (s or "").strip())[:max_len]

            name        = _clean(session.get("name")        or "Candidate", 100)
            jd          = _clean(session.get("jd")          or "", 4000)
            phone       = _clean(session.get("phone")       or "", 20)
            resume_text = _clean(session.get("resume_text") or "", 8000)
            raw_voice   = _clean(session.get("voice_id")    or DEFAULT_VOICE_ID, 20)
            voice_id    = raw_voice if raw_voice in VOICE_PROFILES else DEFAULT_VOICE_ID
            voice_profile = VOICE_PROFILES[voice_id]
            # Pre-seed call_sid from session so _mark_ended works even if Twilio
            # "start" event never arrives (e.g. WebSocket drops before media stream opens).
            call_sid    = _clean(session.get("call_sid") or "", 50)

            if not jd or len(jd.strip()) < 20:
                logger.warning("[Twilio] No usable JD in session — using default JD")
                jd = _DEFAULT_JD

            # Retry context (populated on call 2 & 3)
            retry_num        = int(session.get("retry_num", 0))
            prior_transcript = session.get("prior_transcript", [])
            prior_notes      = session.get("prior_notes", {})

            # Structured recruiter inputs from UI form (may be None)
            recruiter_inputs = session.get("recruiter_inputs") or None

            self._phone            = phone
            self._name             = name
            self._jd               = jd
            self._retry_num        = retry_num
            self._resume_text      = resume_text
            self._recruiter_inputs = recruiter_inputs
            self._voice_id         = voice_id

            logger.info("[Twilio] attempt=%d/3 | phone=%s | name=%s | resume=%s", retry_num + 1, phone, name, bool(resume_text))

            # Use pre-cached JD context parsed while phone was ringing (fast path)
            context: InterviewContext | None = None
            if token:
                cached = await sync_to_async(cache.get)(f"vox:context:{token}")
                if cached:
                    context = InterviewContext.from_dict(cached)
                    logger.info("[Twilio] Pre-cached context loaded status=%s", context.recruiter_status)

            if context is None:
                # Fallback: parse JD now (phone answered before pre-cache finished)
                manager = AgentManager(session_id=self.channel_name)
                context = await manager.prepare_session(
                    jd=jd, candidate_name=name, recruiter_inputs=recruiter_inputs
                )

            logger.info("[Twilio] Recruiter: %s | skills=%s", context.recruiter_status, context.required_skills[:3])

            # Build system prompt — inject JD intelligence + resume + prior context on retries
            if jd:
                system_prompt = build_enriched_system_prompt(
                    name, jd, context, resume_text=resume_text, voice_profile=voice_profile
                )
            else:
                system_prompt = RECRUITER_PROMPT.strip()

            if retry_num > 0 and prior_transcript:
                system_prompt += CallRetryManager.build_continuity_section(
                    prior_transcript, prior_notes
                )
                logger.info("[Twilio] Context continuity injected — %d prior lines, %d captured notes", len(prior_transcript), len(prior_notes))

            # Greeting kickoff — reconnect line on retries, standard opener otherwise
            if retry_num > 0:
                reconnect = CallRetryManager.reconnect_greeting(name, retry_num)
                greeting_kickoff = (
                    f"Open with EXACTLY this line and nothing else first: "
                    f'"{reconnect}" — then naturally continue the conversation '
                    f"based on the CALL CONTINUITY section in your system prompt."
                )
                logger.info("[Twilio] Reconnect greeting: %s", reconnect)
            elif jd:
                greeting_kickoff = build_vox_greeting_kickoff(name)
            else:
                greeting_kickoff = SARAH_GREETING_KICKOFF

            self.bridge = GeminiLiveBridge(
                mode="twilio",
                system_prompt=system_prompt,
                greeting_kickoff=greeting_kickoff,
                on_send_twilio_json=self._send_twilio_json,
                on_call_ended=self._handle_call_ended,
                finalize_consumer=self,
                candidate_name=name,
                candidate_phone=phone,
                job_description=jd,
                call_sid=call_sid,
                call_channel="twilio",
                interview_context=context,
                resume_text=resume_text,
                voice_id=voice_id,
            )
            self._bridge_task = asyncio.create_task(self.bridge.run())
            logger.info("[Twilio] Gemini Live bridge started.")

        except Exception as e:
            logger.error("[Twilio] Connection failed: %s", e)
            await self.close()

    # ------------------------------------------------------------------
    # Retry callback — fires after _finalize() with full flushed transcript
    # ------------------------------------------------------------------

    async def _handle_call_ended(self, was_dropped: bool, duration_seconds: float) -> None:
        transcript = getattr(self.bridge, "transcript", [])
        logger.info("[Twilio] Call ended — dropped=%s duration=%.1fs turns=%d attempt=%d/3", was_dropped, duration_seconds, len(transcript), self._retry_num + 1)

        if not was_dropped:
            # Short natural close = wrong person picked up, candidate unavailable
            # A real screening ends in 60s+ even for a quick "not interested"
            if duration_seconds < 30:
                was_dropped = True
                logger.info("[Retry] Short natural close (%.0fs) — likely wrong person/unavailable, treating as retriable", duration_seconds)
            else:
                # Natural close after real screening — clear retry state and done
                await sync_to_async(CallRetryManager.clear)(self._phone)
                return

        if not self._phone:
            logger.warning("[Retry] No phone number on session — cannot retry")
            return

        if self._retry_num >= CallRetryManager.MAX_RETRIES:
            logger.info("[Retry] Max retries reached for %s — no further callbacks", self._phone)
            await sync_to_async(CallRetryManager.clear)(self._phone)
            return

        # Save drop context (accumulates transcript across retries)
        retry_num = await sync_to_async(CallRetryManager.record_drop)(
            phone=self._phone,
            name=self._name,
            jd=self._jd,
            transcript=transcript,
            notes={},   # Gemini path doesn't use silent tools; notes come from transcript
            resume_text=self._resume_text,
            recruiter_inputs=self._recruiter_inputs,
            voice_id=getattr(self, "_voice_id", DEFAULT_VOICE_ID),
        )

        host_url = os.getenv("PUBLIC_URL", "").strip()
        from_number = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

        if not host_url or not from_number:
            logger.warning("[Retry] PUBLIC_URL or TWILIO_PHONE_NUMBER not set — cannot retry")
            return

        delay = RETRY_1_DELAY if retry_num == 1 else RETRY_2_DELAY
        delay_label = "immediately (~5s)" if retry_num == 1 else "in 5 minutes"
        logger.info("[Retry] Scheduling callback #%d to %s %s", retry_num, self._phone, delay_label)

        state = await sync_to_async(CallRetryManager.load)(self._phone)
        CallRetryManager.schedule_callback(
            phone=self._phone,
            name=self._name,
            jd=self._jd,
            transcript=state.get("transcript", transcript),
            notes=state.get("notes", {}),
            resume_text=state.get("resume_text", self._resume_text),
            recruiter_inputs=state.get("recruiter_inputs", self._recruiter_inputs),
            voice_id=state.get("voice_id", getattr(self, "_voice_id", DEFAULT_VOICE_ID)),
            retry_num=retry_num,
            delay_seconds=delay,
            host_url=host_url,
            from_number=from_number,
        )

    async def send_recap(self, score, reason) -> None:
        """Twilio sessions have no live UI — score is saved to DB only."""
        logger.info("[Twilio] Session finalized — score=%s", score)

    # ------------------------------------------------------------------
    # WebSocket plumbing
    # ------------------------------------------------------------------

    def _parse_query(self) -> dict:
        raw = self.scope.get("query_string", b"")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        logger.info("[Twilio] raw query_string: %r", raw)
        parsed = parse_qs(raw, keep_blank_values=True)
        # parse_qs returns {key: [list]}, flatten to {key: first_value}
        return {k: v[0] for k, v in parsed.items() if v}

    async def disconnect(self, close_code):
        logger.info("[Twilio] Disconnected (code=%s)", close_code)
        if hasattr(self, "bridge"):
            call_sid = getattr(self.bridge, "_call_sid", "")
            self.bridge.close()
            # Mark call ended immediately so the UI poll can detect it within seconds,
            # before the slow evaluation/DB write completes (can take 10-30s)
            if call_sid:
                await sync_to_async(cache.set)(f"vox:ended:{call_sid}", True, timeout=3600)
                print(f"[Twilio] Marked call {call_sid} as ended in cache")
        if hasattr(self, "_bridge_task") and not self._bridge_task.done():
            try:
                # Wait for the bridge to finalize naturally so _finalize() runs:
                # it schedules the retry callback first, then saves to DB via
                # Gemini summary (~5-20s).  30s gives ample headroom.
                await asyncio.wait_for(self._bridge_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("[Twilio] Bridge finalize timed out — force-cancelling")
                self._bridge_task.cancel()
                try:
                    await self._bridge_task
                except Exception:
                    pass
            except Exception:
                pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if hasattr(self, "bridge") and self.bridge:
            # enqueue_twilio_event already guards against a closed bridge internally
            self.bridge.enqueue_twilio_event(data)

    async def _send_twilio_json(self, payload: dict) -> None:
        await self.send(text_data=json.dumps(payload))
