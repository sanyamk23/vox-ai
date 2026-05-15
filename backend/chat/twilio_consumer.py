import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from .agent import VoiceAgent

class TwilioConsumer(AsyncWebsocketConsumer):
    """
    Handles Real-time Phone Calls via Twilio Media Streams.
    """
    async def connect(self):
        try:
            print("[Twilio] Incoming Call Stream Connecting...")
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
            # Deepgram needs to know we are sending mulaw for Twilio
            await self.agent.start_pipeline(encoding="mulaw")
            self.stream_sid = None
            print("[Twilio] Connection Established and Pipeline Started.")
        except Exception as e:
            print(f"[Twilio-CRITICAL] Connection Failed: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        print(f"[Twilio] Call Ended: {close_code}")
        if hasattr(self, 'agent'):
            await self.agent.stop_pipeline()

    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if data['event'] == 'start':
            self.stream_sid = data['start']['streamSid']
            print(f"[Twilio] Stream Started: {self.stream_sid}")
            # Trigger greeting ONLY when we have a valid streamSid
            await self.agent.initial_greeting()
            
        elif data['event'] == 'media':
            # Twilio sends base64 encoded mulaw
            payload = data['media']['payload']
            chunk = base64.b64decode(payload)
            await self.agent.process_audio_chunk(chunk)
            
        elif data['event'] == 'stop':
            print("[Twilio] Stream Stopped.")
            await self.close()

    async def send_audio(self, chunk: bytes):
        """
        Sends audio back to the phone line.
        Note: Twilio expects 8000Hz mulaw. 
        For the hackathon, we stream back raw for Web, 
        but this is the hook for Twilio 'play' events.
        """
        if self.stream_sid:
            base64_audio = base64.b64encode(chunk).decode('utf-8')
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {
                    "payload": base64_audio
                }
            }
            await self.send(text_data=json.dumps(message))

    async def send_transcript(self, role: str, text: str):
        # Transcripts aren't sent to the phone, but we log them for the dashboard
        print(f"[Twilio-Live] {role}: {text}")

    async def send_interrupt(self):
        # Clears the Twilio stream buffer
        if self.stream_sid:
            await self.send(text_data=json.dumps({
                "event": "clear",
                "streamSid": self.stream_sid
            }))

    async def send_recap(self, score, reason):
        print(f"[Twilio-Final] Score: {score}")
