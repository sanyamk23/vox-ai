"""
Speech-to-Text Service (Open/Closed Principle).

Abstracts Deepgram STT behind a clean interface so the VoiceAgent
doesn't know or care about the STT provider.
"""
from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Optional

from deepgram import AsyncDeepgramClient

logger = logging.getLogger("vox.stt")


# ─── Audio Encoding Config (DRY) ─────────────────────────────────────────────

class AudioConfig:
    """Encapsulates encoding-specific parameters. Used by both STT and TTS."""

    def __init__(self, encoding: str = "linear16"):
        self.encoding = encoding

    @property
    def sample_rate(self) -> int:
        return 8000 if self.encoding == "mulaw" else 16000

    @property
    def is_telephony(self) -> bool:
        return self.encoding == "mulaw"


# ─── Abstract Base ───────────────────────────────────────────────────────────

class BaseSTTService(ABC):
    """Extend to swap STT providers without modifying VoiceAgent."""

    @abstractmethod
    async def start(
        self,
        audio_config: AudioConfig,
        on_transcript: Callable,
    ) -> None:
        """Open a streaming connection and begin listening."""
        ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """Feed an audio chunk to the STT stream."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully close the STT stream."""
        ...


# ─── Deepgram Implementation ─────────────────────────────────────────────────

class DeepgramSTTService(BaseSTTService):
    """
    Real-time STT using Deepgram Nova-2.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        self._client = AsyncDeepgramClient(api_key=self._api_key)
        self._context = None
        self._connection = None
        self._listener_task = None

    async def start(
        self,
        audio_config: AudioConfig,
        on_transcript: Callable,
    ) -> None:
        """
        Open a persistent WebSocket to Deepgram and register the transcript callback.

        Args:
            audio_config: Encoding and sample rate configuration.
            on_transcript: async callback(transcript: str, is_final: bool)
        """
        logger.info(
            f"[STT] Starting Deepgram (encoding={audio_config.encoding}, "
            f"rate={audio_config.sample_rate})"
        )

        self._context = self._client.listen.v1.connect(
            model="nova-2",
            smart_format=True,
            language="en-IN",
            encoding=audio_config.encoding,
            sample_rate=audio_config.sample_rate,
            interim_results=True,
            vad_events=True,
            endpointing=300,
        )
        self._connection = await self._context.__aenter__()

        async def _on_message(result, **kwargs):
            try:
                transcript = ""
                is_final = False
                if hasattr(result, "channel"):
                    transcript = result.channel.alternatives[0].transcript
                    is_final = result.is_final
                if transcript:
                    await on_transcript(transcript, is_final)
            except Exception as e:
                logger.error(f"[STT] Transcript callback error: {e}")

        self._connection.on("message", _on_message)
        self._listener_task = asyncio.create_task(self._connection.start_listening())

    async def send_audio(self, chunk: bytes) -> None:
        """Feed raw audio bytes to the Deepgram stream."""
        if self._connection:
            try:
                await self._connection.send_media(chunk)
            except Exception as e:
                logger.error(f"[STT] Send audio error: {e}")

    async def stop(self) -> None:
        """Close the Deepgram connection."""
        if self._listener_task:
            self._listener_task.cancel()
        if self._context:
            try:
                await self._context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[STT] Cleanup warning: {e}")
        logger.info("[STT] Stopped")
