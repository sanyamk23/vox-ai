import json
from urllib.parse import unquote
from channels.generic.websocket import AsyncWebsocketConsumer
from .agent import VoiceAgent


class VoiceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("[WebSocket] Connecting...")
        params = self._parse_query()
        await self.accept()
        self.agent = VoiceAgent(
            self,
            job_description=params.get("jd"),
            candidate_name=params.get("name"),
            candidate_phone=params.get("phone"),
            call_channel="web",
        )
        await self.agent.start_pipeline()
        await self.agent.initial_greeting()
        print("[WebSocket] Connected.")

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
        if hasattr(self, "agent"):
            await self.agent.stop_pipeline()

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data:
            await self.agent.process_audio_chunk(bytes_data)
        elif text_data:
            try:
                data = json.loads(text_data)
                if data.get("type") == "stop":
                    await self.agent.stop_pipeline()
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
