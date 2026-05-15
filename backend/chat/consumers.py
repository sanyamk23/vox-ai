import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .agent import VoiceAgent

class VoiceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("[WebSocket] Connecting...")
        query_params = self.scope.get('query_string', b'').decode()
        jd = None
        name = None
        if 'jd=' in query_params:
            from urllib.parse import unquote
            jd = unquote(query_params.split('jd=')[1].split('&')[0])
        if 'name=' in query_params:
            from urllib.parse import unquote
            name = unquote(query_params.split('name=')[1].split('&')[0])

        await self.accept()
        self.agent = VoiceAgent(self, job_description=jd, candidate_name=name)
        await self.agent.start_pipeline()
        await self.agent.initial_greeting()
        print("[WebSocket] Connected.")

    async def disconnect(self, close_code):
        print(f"[WebSocket] Disconnected: {close_code}")
        if hasattr(self, 'agent'):
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
        await self.send(text_data=json.dumps({
            "type": "transcript",
            "role": role,
            "text": text
        }))

    async def send_interrupt(self):
        await self.send(text_data=json.dumps({
            "type": "interrupt"
        }))

    async def send_recap(self, score, reason):
        await self.send(text_data=json.dumps({
            "type": "recap",
            "data": {
                "score": score,
                "reason": reason
            }
        }))
