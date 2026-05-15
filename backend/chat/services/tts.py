"""
Text-to-Speech Service (Open/Closed Principle).

Abstracts Deepgram TTS behind a clean interface. Reuses AudioConfig
from stt.py for encoding consistency (DRY).
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

from .stt import AudioConfig

logger = logging.getLogger("vox.tts")


# ─── Abstract Base ───────────────────────────────────────────────────────────

class BaseTTSService(ABC):
    """Extend to swap TTS providers without modifying VoiceAgent."""

    @abstractmethod
    async def synthesize(self, text: str) -> Optional[bytes]:
        """Convert text to audio bytes. Returns None on failure."""
        ...


# ─── Deepgram Implementation ─────────────────────────────────────────────────

DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"


class DeepgramTTSService(BaseTTSService):
    """
    TTS using Deepgram Aura-Orpheus.
    Reuses AudioConfig for encoding-aware synthesis.
    """

    def __init__(
        self,
        audio_config: AudioConfig,
        model: str = "aura-orpheus-en",
        api_key: Optional[str] = None,
    ):
        self._audio_config = audio_config
        self._model = model
        self._api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        self._headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
        }

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert text to audio bytes using Deepgram TTS.
        Returns raw audio bytes or None on failure.
        """
        if not text:
            return None

        url = (
            f"{DEEPGRAM_TTS_URL}"
            f"?model={self._model}"
            f"&encoding={self._audio_config.encoding}"
            f"&sample_rate={self._audio_config.sample_rate}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json={"text": text}, headers=self._headers
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        body = await resp.text()
                        logger.error(
                            f"[TTS] Deepgram returned {resp.status}: {body[:200]}"
                        )
                        return None
        except Exception as e:
            logger.error(f"[TTS] Synthesis failed for '{text[:50]}...': {e}")
            return None
