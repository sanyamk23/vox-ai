import asyncio
import json
import logging
import os
from urllib.parse import unquote

from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache

from .agent import build_enriched_system_prompt, VOX_GREETING_KICKOFF
from .agents.manager import AgentManager
from .gemini_recruiter import (
    GeminiLiveBridge,
    RECRUITER_PROMPT,
    SARAH_GREETING_KICKOFF,
)
from .retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY

logger = logging.getLogger(__name__)

_DEFAULT_JD = "Software Engineer at a high-growth startup."


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
            await self.accept()
            print("[Twilio] Socket connected successfully.")

            params = self._parse_query()
            session = {}
            token = params.get("token", "")
            if token:
                session = cache.get(f"vox:{token}") or {}
                if not session:
                    logger.warning("[Twilio] Cache miss for token=%s — falling back to query params / defaults", token)

            name        = session.get("name")        or params.get("name")        or "Candidate"
            jd          = session.get("jd")          or params.get("jd")          or ""
            phone       = session.get("phone")       or params.get("phone")       or ""
            resume_text = session.get("resume_text") or params.get("resume_text") or ""

            if not jd or len(jd.strip()) < 20:
                logger.warning(
                    "[Twilio] No usable JD on session (cache=%s, params=%s) — using default JD",
                    bool(session.get("jd")), bool(params.get("jd")),
                )
                jd = _DEFAULT_JD

            # Retry context (populated on call 2 & 3)
            retry_num        = int(session.get("retry_num", 0))
            prior_transcript = session.get("prior_transcript", [])
            prior_notes      = session.get("prior_notes", {})

            # Structured recruiter inputs from UI form (may be None)
            recruiter_inputs = session.get("recruiter_inputs") or None

            self._phone        = phone
            self._name         = name
            self._jd           = jd
            self._retry_num    = retry_num
            self._resume_text  = resume_text

            print(
                f"[Twilio] attempt={retry_num + 1}/3 | phone={phone} | name={name} | resume={bool(resume_text)}"
            )

            # Pre-call: parse JD → InterviewContext (guaranteed to return)
            manager = AgentManager(session_id=self.channel_name)
            context = await manager.prepare_session(
                jd=jd, candidate_name=name, recruiter_inputs=recruiter_inputs
            )
            print(
                f"[Twilio] Recruiter: {context.recruiter_status} | "
                f"skills={context.required_skills[:3]}"
            )

            # Build system prompt — inject JD intelligence + resume + prior context on retries
            if jd:
                system_prompt = build_enriched_system_prompt(name, jd, context, resume_text=resume_text)
            else:
                system_prompt = RECRUITER_PROMPT.strip()

            if retry_num > 0 and prior_transcript:
                system_prompt += CallRetryManager.build_continuity_section(
                    prior_transcript, prior_notes
                )
                print(
                    f"[Twilio] Context continuity injected — "
                    f"{len(prior_transcript)} prior lines, "
                    f"{len(prior_notes)} captured notes"
                )

            # Greeting kickoff — reconnect line on retries, standard opener otherwise
            if retry_num > 0:
                reconnect = CallRetryManager.reconnect_greeting(name, retry_num)
                greeting_kickoff = (
                    f"Open with EXACTLY this line and nothing else first: "
                    f'"{reconnect}" — then naturally continue the conversation '
                    f"based on the CALL CONTINUITY section in your system prompt."
                )
                print(f"[Twilio] Reconnect greeting: {reconnect}")
            elif jd:
                greeting_kickoff = VOX_GREETING_KICKOFF
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
                call_channel="twilio",
                interview_context=context,
                resume_text=resume_text,
            )
            self._bridge_task = asyncio.create_task(self.bridge.run())
            print("[Twilio] Gemini Live bridge started.")

        except Exception as e:
            print(f"[Twilio] Connection failed: {e}")
            await self.close()

    # ------------------------------------------------------------------
    # Retry callback — fires after _finalize() with full flushed transcript
    # ------------------------------------------------------------------

    async def _handle_call_ended(self, was_dropped: bool, duration_seconds: float) -> None:
        transcript = getattr(self.bridge, "transcript", [])
        print(
            f"[Twilio] Call ended — dropped={was_dropped} "
            f"duration={duration_seconds:.1f}s "
            f"turns={len(transcript)} attempt={self._retry_num + 1}/3"
        )

        if not was_dropped:
            # Short natural close = wrong person picked up, candidate unavailable
            # A real screening ends in 60s+ even for a quick "not interested"
            if duration_seconds < 30:
                was_dropped = True
                print(
                    f"[Retry] Short natural close ({duration_seconds:.0f}s) — "
                    "likely wrong person/unavailable, treating as retriable"
                )
            else:
                # Natural close after real screening — clear retry state and done
                CallRetryManager.clear(self._phone)
                return

        if not self._phone:
            print("[Retry] No phone number on session — cannot retry")
            return

        if self._retry_num >= CallRetryManager.MAX_RETRIES:
            print(f"[Retry] Max retries reached for {self._phone} — no further callbacks")
            CallRetryManager.clear(self._phone)
            return

        # Save drop context (accumulates transcript across retries)
        retry_num = CallRetryManager.record_drop(
            phone=self._phone,
            name=self._name,
            jd=self._jd,
            transcript=transcript,
            notes={},   # Gemini path doesn't use silent tools; notes come from transcript
            resume_text=self._resume_text,
        )

        host_url = os.getenv("PUBLIC_URL", "").strip()
        from_number = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

        if not host_url or not from_number:
            print("[Retry] PUBLIC_URL or TWILIO_PHONE_NUMBER not set — cannot retry")
            return

        delay = RETRY_1_DELAY if retry_num == 1 else RETRY_2_DELAY
        delay_label = "immediately (~5s)" if retry_num == 1 else "in 5 minutes"
        print(f"[Retry] Scheduling callback #{retry_num} to {self._phone} {delay_label}")

        state = CallRetryManager.load(self._phone)
        CallRetryManager.schedule_callback(
            phone=self._phone,
            name=self._name,
            jd=self._jd,
            transcript=state.get("transcript", transcript),
            notes=state.get("notes", {}),
            resume_text=state.get("resume_text", self._resume_text),
            retry_num=retry_num,
            delay_seconds=delay,
            host_url=host_url,
            from_number=from_number,
        )

    async def send_recap(self, score, reason) -> None:
        """Twilio sessions have no live UI — score is saved to DB only."""
        print(f"[Twilio] Session finalized — score={score}")

    # ------------------------------------------------------------------
    # WebSocket plumbing
    # ------------------------------------------------------------------

    def _parse_query(self) -> dict:
        raw = self.scope.get("query_string", b"").decode()
        result = {}
        for part in raw.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = unquote(v)
        return result

    async def disconnect(self, close_code):
        print(f"[Twilio] Disconnected (code={close_code})")
        if hasattr(self, "bridge"):
            self.bridge.close()
        if hasattr(self, "_bridge_task") and not self._bridge_task.done():
            try:
                # Wait for the bridge to finalize naturally so _finalize() runs:
                # it schedules the retry callback first, then saves to DB via
                # Gemini summary (~5-20s).  30s gives ample headroom.
                await asyncio.wait_for(self._bridge_task, timeout=30.0)
            except asyncio.TimeoutError:
                print("[Twilio] Bridge finalize timed out — force-cancelling")
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

        # Ensure bridge is initialized before enqueuing
        if hasattr(self, "bridge") and self.bridge:
            self.bridge.enqueue_twilio_event(data)
        else:
            # If we get media before bridge is ready, it's rare but possible
            event = data.get("event")
            if event == "media":
                pass # Drop or could buffer if critical

    async def _send_twilio_json(self, payload: dict) -> None:
        await self.send(text_data=json.dumps(payload))
