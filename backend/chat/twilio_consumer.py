import json
import base64
from urllib.parse import unquote
from channels.generic.websocket import AsyncWebsocketConsumer
from .agent import VoiceAgent


class TwilioConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            await self.accept()
            print("[Twilio] Call stream connected.")

            params = self._parse_query()
            self.stream_sid = None
            self.agent = VoiceAgent(
                self,
                job_description=params.get("jd"),
                candidate_name=params.get("name"),
                candidate_phone=params.get("phone"),
                call_channel="twilio",
            )
            await self.agent.start_pipeline(encoding="mulaw")
            print("[Twilio] Pipeline started, waiting for stream start event.")

        except Exception as e:
            print(f"[Twilio-CRITICAL] Connection failed: {e}")
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
        print(f"[Twilio] Call ended (code={close_code})")
        if hasattr(self, "agent"):
            await self.agent.stop_pipeline()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            return
        event = data.get("event")

        if event == "start":
            start = data.get("start", {})
            self.stream_sid = start.get("streamSid", "")
            self.agent.call_sid = start.get("callSid", "")
            print(f"[Twilio] Stream started: {self.stream_sid} | Call: {self.agent.call_sid}")
            await self.agent.initial_greeting()

        elif event == "media":
            try:
                payload = data.get("media", {}).get("payload", "")
                if payload:
                    chunk = base64.b64decode(payload)
                    await self.agent.process_audio_chunk(chunk)
            except Exception as e:
                print(f"[Twilio] Bad media chunk: {e}")

        elif event == "stop":
            print("[Twilio] Stream stopped.")
            await self.close()

    async def send_audio(self, chunk: bytes):
        if self.stream_sid:
            await self.send(text_data=json.dumps({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode("utf-8")},
            }))

    async def send_transcript(self, role: str, text: str):
        print(f"[Twilio-Live] {role}: {text}")

    async def send_interrupt(self):
        if self.stream_sid:
            await self.send(text_data=json.dumps({
                "event": "clear",
                "streamSid": self.stream_sid,
            }))

    async def send_recap(self, score, reason):
        print(f"[Twilio-Final] Score={score} | {reason[:200]}")
