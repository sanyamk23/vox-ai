import asyncio
import json
from urllib.parse import unquote

from channels.generic.websocket import AsyncWebsocketConsumer

from .agent import build_enriched_system_prompt
from .agents.manager import AgentManager
from .gemini_recruiter import GeminiLiveBridge


class VoiceConsumer(AsyncWebsocketConsumer):
    """Web microphone session — Gemini Live with Priya system prompt."""

    async def connect(self):
        print("[WebSocket] Connecting...")
        params = self._parse_query()
        await self.accept()

        self._name = params.get("name") or "there"
        self._jd = params.get("jd") or "Software Engineer at a high-growth startup."
        self._phone = params.get("phone") or ""

        # Pre-call: parse JD → InterviewContext (guaranteed to return even on failure)
        manager = AgentManager(session_id=self.channel_name)
        context = await manager.prepare_session(jd=self._jd, candidate_name=self._name)
        print(
            f"[WebSocket] Recruiter: {context.recruiter_status} | "
            f"skills={context.required_skills[:3]}"
        )

        self.bridge = GeminiLiveBridge(
            mode="web",
            system_prompt=build_enriched_system_prompt(self._name, self._jd, context),
            on_send_web_audio=self.send_audio,
            on_transcript=self.send_transcript,
            on_interrupt=self.send_interrupt,
            on_ready=self._send_ready,
            finalize_consumer=self,
            candidate_name=self._name,
            candidate_phone=self._phone,
            job_description=self._jd,
            call_channel="web",
            interview_context=context,
        )
        self._bridge_task = asyncio.create_task(self._run_bridge())

    async def _run_bridge(self):
        try:
            await self.bridge.run()
        except Exception as e:
            print(f"[WebSocket] Gemini bridge failed: {e}")
            try:
                await self.send(text_data=json.dumps({"type": "error", "message": str(e)}))
            except Exception:
                pass
            await self.close()

    async def _send_ready(self):
        await self.send(text_data=json.dumps({"type": "ready"}))
        print("[WebSocket] Gemini ready — client may start microphone.")

    def _parse_query(self) -> dict:
        raw = self.scope.get("query_string", b"").decode()
        result = {}
        for part in raw.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = unquote(v)
        return result

    async def disconnect(self, close_code):
        print(f"[WebSocket] Disconnected (code={close_code})")
        if hasattr(self, "bridge"):
            self.bridge.close()
        if hasattr(self, "_bridge_task") and not self._bridge_task.done():
            try:
                await asyncio.wait_for(self._bridge_task, timeout=10.0)
            except asyncio.TimeoutError:
                print("[WebSocket] Bridge finalize timed out — force-cancelling")
                self._bridge_task.cancel()
                try:
                    await self._bridge_task
                except Exception:
                    pass
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data and hasattr(self, "bridge"):
            self.bridge.feed_pcm(bytes_data)
        elif text_data:
            try:
                data = json.loads(text_data)
                if data.get("type") == "stop" and hasattr(self, "bridge"):
                    self.bridge.close()
            except Exception:
                pass

    async def send_audio(self, chunk: bytes):
        await self.send(bytes_data=chunk)

    async def send_transcript(self, role: str, text: str):
        await self.send(text_data=json.dumps({"type": "transcript", "role": role, "text": text}))

    async def send_interrupt(self):
        await self.send(text_data=json.dumps({"type": "interrupt"}))

    async def send_recap(self, score, reason):
        await self.send(text_data=json.dumps({"type": "recap", "data": {"score": score, "reason": reason}}))


