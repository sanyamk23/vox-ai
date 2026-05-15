"""
VoiceAgent — The orchestrator.

This class is now a thin coordinator. All heavy lifting is delegated to
the service layer (STT, TTS, LLM, Prompt). It manages conversation state,
backchannel timing, and interrupt logic.

Principles applied:
- DRY: STT/TTS/LLM/Prompt logic lives in services, not here.
- Open/Closed: Swap any service via constructor injection.
- Single Responsibility: Agent orchestrates; services do the work.
"""
from __future__ import annotations

import asyncio
import logging
import time
import random
from typing import Optional

from opentelemetry import trace

from .services.stt import AudioConfig, DeepgramSTTService, BaseSTTService
from .services.tts import DeepgramTTSService, BaseTTSService
from .services.llm import (
    GroqLLMService,
    BaseLLMService,
    stream_sentences,
    maybe_summarize_history,
    generate_scorecard,
)
from .services.prompt import PromptBuilder

logger = logging.getLogger("vox.agent")
tracer = trace.get_tracer(__name__)

# ─── Backchannel Config ──────────────────────────────────────────────────────

BACKCHANNEL_COOLDOWN = 4.0  # seconds between backchannels
BACKCHANNEL_PHRASES = ["I see", "Right", "Mm-hmm", "Okay", "Got it", "Sure"]
INTERRUPT_MIN_LENGTH = 2    # min transcript length to trigger interrupt


class VoiceAgent:
    """
    Orchestrates a single voice screening session.

    Services are injected via constructor — pass custom implementations
    to swap providers without modifying this class (Open/Closed).
    """

    def __init__(
        self,
        consumer,
        session_id: str = "default",
        job_description: Optional[str] = None,
        candidate_name: Optional[str] = None,
        company_name: Optional[str] = None,
        # Service injection points (Open/Closed)
        stt_service: Optional[BaseSTTService] = None,
        tts_service: Optional[BaseTTSService] = None,
        llm_service: Optional[BaseLLMService] = None,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.consumer = consumer
        self.session_id = session_id
        self.candidate_name = candidate_name or "Candidate"
        self.company_name = company_name or "the company"
        self.job_description = job_description or "Software Engineer at a high-growth startup."

        # State
        self.is_interrupted = False
        self.is_ai_speaking = False
        self._current_llm_task: Optional[asyncio.Task] = None
        self._last_backchannel_time = time.time()
        self._audio_config: Optional[AudioConfig] = None

        # Services — use defaults if not injected
        self._stt = stt_service or DeepgramSTTService()
        self._llm = llm_service or GroqLLMService()
        self._tts: Optional[BaseTTSService] = tts_service  # Set in start_pipeline
        self._prompt_builder = prompt_builder or PromptBuilder()

        # Build the system prompt
        prompt_context = {
            "candidate_name": self.candidate_name,
            "company_name": self.company_name,
            "job_description": self.job_description,
        }
        system_prompt = self._prompt_builder.build(prompt_context)

        self.chat_history = [
            {"role": "system", "content": system_prompt}
        ]

    # ─── Lifecycle ────────────────────────────────────────────────────────

    async def start_pipeline(self, encoding: str = "linear16") -> None:
        """Boot the STT + TTS services."""
        self._audio_config = AudioConfig(encoding)

        # Initialize TTS with the correct encoding (if not injected)
        if self._tts is None:
            self._tts = DeepgramTTSService(self._audio_config)

        logger.info(
            f"[Agent] Starting pipeline (session={self.session_id}, "
            f"encoding={encoding})"
        )

        # Start STT with our transcript handler
        await self._stt.start(self._audio_config, self._on_transcript)

    async def stop_pipeline(self) -> None:
        """Finalize the session and shut down services."""
        await self._finalize_session()
        await self._stt.stop()
        logger.info(f"[Agent] Pipeline stopped (session={self.session_id})")

    # ─── Greeting ─────────────────────────────────────────────────────────

    async def initial_greeting(self) -> None:
        """Send the opening greeting via transcript + TTS."""
        greeting = (
            f"Hi {self.candidate_name}, this is Vox calling from "
            f"{self.company_name}. I hope I am not catching you at a bad time. "
            f"I am reaching out regarding the role you applied for. "
            f"Do you have a few minutes for a quick screening call?"
        )
        await self.consumer.send_transcript("vox", greeting)
        await self._speak(greeting)
        self.chat_history.append({"role": "assistant", "content": greeting})

    # ─── Audio Input ──────────────────────────────────────────────────────

    async def process_audio_chunk(self, chunk: bytes) -> None:
        """Feed an audio chunk into the STT stream."""
        await self._stt.send_audio(chunk)

    # ─── Transcript Handling (STT Callback) ───────────────────────────────

    async def _on_transcript(self, transcript: str, is_final: bool) -> None:
        """
        Called by the STT service for every transcript result.
        Handles backchannel, interrupts, and triggering LLM responses.
        """
        # Backchannel on interim transcripts when AI is silent
        if not is_final and not self.is_ai_speaking:
            await self._maybe_backchannel()

        # Interrupt detection: candidate speaking while AI is talking
        if transcript.strip() and self.is_ai_speaking:
            if len(transcript) > INTERRUPT_MIN_LENGTH or is_final:
                await self._handle_interrupt()

        # Final transcript → send to chat + trigger LLM
        if is_final:
            await self.consumer.send_transcript("user", transcript)
            await self._trigger_llm_response(transcript)

    # ─── Backchannel Engine ───────────────────────────────────────────────

    async def _maybe_backchannel(self) -> None:
        """Emit a natural backchannel if enough time has passed."""
        now = time.time()
        if now - self._last_backchannel_time > BACKCHANNEL_COOLDOWN:
            phrase = random.choice(BACKCHANNEL_PHRASES)
            await self._speak(phrase)
            self._last_backchannel_time = now

    # ─── Interrupt Handling ───────────────────────────────────────────────

    async def _handle_interrupt(self) -> None:
        """Cancel the current LLM task and notify the frontend."""
        if self._current_llm_task and not self._current_llm_task.done():
            self._current_llm_task.cancel()
        self.is_ai_speaking = False
        self.is_interrupted = True
        await self.consumer.send_interrupt()
        logger.debug("[Agent] Interrupt triggered")

    # ─── LLM Response Loop ───────────────────────────────────────────────

    async def _trigger_llm_response(self, user_text: str) -> None:
        """Queue a new LLM response, cancelling any in-progress one."""
        self.is_interrupted = False
        self.is_ai_speaking = True
        self.chat_history.append({"role": "user", "content": user_text})

        # Context window management
        self.chat_history = await maybe_summarize_history(
            self._llm, self.chat_history
        )

        # Cancel any in-flight response
        if self._current_llm_task and not self._current_llm_task.done():
            self._current_llm_task.cancel()

        self._current_llm_task = asyncio.create_task(self._run_llm_loop())

    async def _run_llm_loop(self) -> None:
        """
        Stream the LLM response sentence-by-sentence through TTS.
        Uses the service-layer stream_sentences helper (DRY).
        """
        full_response = ""

        try:
            async for sentence in stream_sentences(self._llm, self.chat_history):
                if self.is_interrupted:
                    break
                await self._speak(sentence)
                full_response += sentence + " "

            # Record the complete response in chat history
            if full_response.strip() and not self.is_interrupted:
                clean_response = full_response.strip()
                await self.consumer.send_transcript("vox", clean_response)
                self.chat_history.append(
                    {"role": "assistant", "content": clean_response}
                )

        except asyncio.CancelledError:
            logger.debug("[Agent] LLM loop cancelled (interrupt)")
        except Exception as e:
            logger.error(f"[Agent] LLM loop error: {e}", exc_info=True)
        finally:
            self.is_ai_speaking = False

    # ─── TTS Helper ───────────────────────────────────────────────────────

    async def _speak(self, text: str) -> None:
        """Synthesize text and send audio to the consumer."""
        if self.is_interrupted or not text:
            return
        audio = await self._tts.synthesize(text)
        if audio:
            await self.consumer.send_audio(audio)

    # ─── Session Finalization ─────────────────────────────────────────────

    async def _finalize_session(self) -> None:
        """
        Generate a structured scorecard from the conversation.
        Uses proper JSON parsing instead of the old regex approach.
        """
        try:
            scorecard = await generate_scorecard(self._llm, self.chat_history)
            score = scorecard.get("intent_score", "N/A")
            await self.consumer.send_recap(score, scorecard)
        except Exception as e:
            logger.error(f"[Agent] Finalization error: {e}", exc_info=True)
            await self.consumer.send_recap("N/A", {"error": str(e)})
