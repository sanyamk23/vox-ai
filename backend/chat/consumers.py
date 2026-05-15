"""
WebSocket Consumers for Project Vox.

DRY: Shared logic (query parsing, agent lifecycle) lives in BaseVoiceConsumer.
Each subclass only implements transport-specific behavior.
"""
from __future__ import annotations

import json
import base64
import logging
from abc import abstractmethod

from channels.generic.websocket import AsyncWebsocketConsumer

from .agent import VoiceAgent
from .utils import parse_query_params

logger = logging.getLogger("vox.consumer")


# ─── Base Consumer (DRY) ─────────────────────────────────────────────────────

class BaseVoiceConsumer(AsyncWebsocketConsumer):
    """
    Shared foundation for Web and Twilio consumers.
    Subclasses only override transport-specific methods.
    """

    # Subclasses set this to configure audio encoding
    default_encoding: str = "linear16"

    async def _init_agent(self) -> None:
        """Parse query params and boot the VoiceAgent. Shared by all consumers."""
        params = parse_query_params(self.scope)
        self.agent = VoiceAgent(
            consumer=self,
            job_description=params["jd"],
            candidate_name=params["name"],
            company_name=params["company"],
        )
        await self.agent.start_pipeline(encoding=self.default_encoding)

    async def disconnect(self, close_code):
        """Shared disconnect — stop the agent pipeline."""
        logger.info(f"[{self.__class__.__name__}] Disconnected: {close_code}")
        if hasattr(self, "agent"):
            await self.agent.stop_pipeline()

    # ── Abstract transport methods (subclasses implement) ─────────────────

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """Send audio back to the client (format depends on transport)."""
        ...

    @abstractmethod
    async def send_transcript(self, role: str, text: str) -> None:
        """Send a transcript message to the client."""
        ...

    @abstractmethod
    async def send_interrupt(self) -> None:
        """Signal the client to flush its audio buffer."""
        ...

    @abstractmethod
    async def send_recap(self, score, reason) -> None:
        """Send the session scorecard to the client."""
        ...


# ─── Web Consumer ─────────────────────────────────────────────────────────────

class VoiceConsumer(BaseVoiceConsumer):
    """
    Browser-based voice sessions.
    Audio: raw PCM bytes over WebSocket.
    Transcripts/events: JSON text messages.
    """

    default_encoding = "linear16"

    async def connect(self):
        logger.info("[WebSocket] Connecting...")
        await self.accept()
        await self._init_agent()
        await self.agent.initial_greeting()
        logger.info("[WebSocket] Connected.")

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data:
            await self.agent.process_audio_chunk(bytes_data)
        elif text_data:
            try:
                data = json.loads(text_data)
                if data.get("type") == "stop":
                    await self.agent.stop_pipeline()
            except json.JSONDecodeError:
                logger.warning("[WebSocket] Received invalid JSON")

    async def send_audio(self, chunk: bytes) -> None:
        await self.send(bytes_data=chunk)

    async def send_transcript(self, role: str, text: str) -> None:
        await self.send(text_data=json.dumps({
            "type": "transcript",
            "role": role,
            "text": text,
        }))

    async def send_interrupt(self) -> None:
        await self.send(text_data=json.dumps({"type": "interrupt"}))

    async def send_recap(self, score, reason) -> None:
        await self.send(text_data=json.dumps({
            "type": "recap",
            "data": {"score": score, "reason": reason},
        }))


# ─── Twilio Consumer ─────────────────────────────────────────────────────────

class TwilioConsumer(BaseVoiceConsumer):
    """
    Phone-based sessions via Twilio Media Streams.
    Audio: base64-encoded mulaw over JSON WebSocket.
    """

    default_encoding = "mulaw"

    async def connect(self):
        try:
            logger.info("[Twilio] Incoming Call Stream Connecting...")
            await self.accept()
            await self._init_agent()
            self.stream_sid = None
            logger.info("[Twilio] Connection Established and Pipeline Started.")
        except Exception as e:
            logger.critical(f"[Twilio] Connection Failed: {e}", exc_info=True)
            await self.close()

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        data = json.loads(text_data)
        event = data.get("event")

        if event == "start":
            self.stream_sid = data["start"]["streamSid"]
            logger.info(f"[Twilio] Stream Started: {self.stream_sid}")
            await self.agent.initial_greeting()

        elif event == "media":
            payload = data["media"]["payload"]
            chunk = base64.b64decode(payload)
            await self.agent.process_audio_chunk(chunk)

        elif event == "stop":
            logger.info("[Twilio] Stream Stopped.")
            await self.close()

    async def send_audio(self, chunk: bytes) -> None:
        """Encode audio as base64 mulaw and send via Twilio media event."""
        if hasattr(self, "stream_sid") and self.stream_sid:
            await self.send(text_data=json.dumps({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode("utf-8")},
            }))

    async def send_transcript(self, role: str, text: str) -> None:
        # Phone calls can't receive JSON — log server-side for the dashboard
        logger.info(f"[Twilio-Live] {role}: {text}")

    async def send_interrupt(self) -> None:
        """Clear the Twilio stream buffer."""
        if hasattr(self, "stream_sid") and self.stream_sid:
            await self.send(text_data=json.dumps({
                "event": "clear",
                "streamSid": self.stream_sid,
            }))

    async def send_recap(self, score, reason) -> None:
        logger.info(f"[Twilio-Final] Score: {score}")
