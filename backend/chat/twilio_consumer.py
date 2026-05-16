import asyncio
import json
from urllib.parse import unquote

from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache

from .gemini_recruiter import (
    GeminiLiveBridge,
    RECRUITER_PROMPT,
    SARAH_GREETING_KICKOFF,
    build_sarah_system_prompt,
)


class TwilioConsumer(AsyncWebsocketConsumer):
    """
    Twilio Media Stream WebSocket — Gemini Live (Sarah recruiter).
    Matches FastAPI /media-stream handler behavior.
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
                    print(f"[Twilio] No session for token={token}")

            name = session.get("name") or params.get("name")
            jd = session.get("jd") or params.get("jd")
            phone = session.get("phone") or params.get("phone") or ""

            # FastAPI uses RECRUITER_PROMPT directly; optional JD/name from session
            system_prompt = (
                build_sarah_system_prompt(jd, name)
                if (jd or name)
                else RECRUITER_PROMPT.strip()
            )

            self.bridge = GeminiLiveBridge(
                mode="twilio",
                system_prompt=system_prompt,
                greeting_kickoff=SARAH_GREETING_KICKOFF,
                on_send_twilio_json=self._send_twilio_json,
                candidate_name=name or "Candidate",
                candidate_phone=phone,
                job_description=jd or "",
                call_channel="twilio",
            )
            self._bridge_task = asyncio.create_task(self.bridge.run())
            print("[Twilio] Gemini Live bridge started.")

        except Exception as e:
            print(f"[Twilio] Connection failed: {e}")
            await self.close()

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
        if hasattr(self, "_bridge_task"):
            self._bridge_task.cancel()
            try:
                await self._bridge_task
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
