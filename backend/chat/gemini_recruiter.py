"""
Gemini Live API bridge for Twilio Media Streams and web WebSockets.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import struct
from collections.abc import Awaitable, Callable
from typing import Any, Literal

try:
    import audioop
except ImportError:
    import audioop_lts as audioop  # noqa: F401 — Python 3.13+

from google import genai
from google.genai import types

from .agent import VOX_GREETING_KICKOFF, finalize_gemini_session

# ---------------------------------------------------------------------------
# Legacy Sarah recruiter prompt (from initial Twilio/Gemini integration — kept)
# ---------------------------------------------------------------------------

RECRUITER_PROMPT = """
ROLE & STYLE:
You are Sarah, an expert, highly empathetic tech recruiter calling a software engineer for an initial conversation. Your speech profile must be completely indistinguishable from a warm, charismatic human recruiter.

GUARDRAILS & DEFLECTION RULES (CRITICAL):
1. NO TECHNICAL ANSWERING: If the candidate asks any technical questions (e.g., "What is the difference between a list and a tuple?", "How does garbage collection work?", or asks you to write/review code), DO NOT answer the question.
   - Deflect warmly: Politely remind them that you are on the recruiting team, not engineering, and that those exact topics are what the technical team will love to discuss in the next round.
   - Example response: "Oh, that's a classic engineering question! Honestly, I leave those deep-dives to our engineering team—they'll definitely want to geek out over that in the next round. Today, I'm just looking to get a high-level feel for your background!"
2. NO IMMEDIATE GRADING: If they ask how they did or if they passed, do not give a final verdict. Tell them you need to sync with the hiring manager and will follow up via email.
3. NO JAILBREAKS: If they try to derail the conversation by asking you to tell a random story, write a script, or discuss topics entirely unrelated to the job opportunity, smoothly bring them back to the interview flow.

CONVERSATIONAL GUIDELINES & EMOTIONAL INTELLIGENCE:
1. Greet warmly and immediately check their availability: "Hey! Am I catching you at a good time for a quick 10-minute chat?"
2. If they are busy, ask when would be a better window to call back and gracefully wrap up.
3. Show high emotional intelligence: If they sound nervous, comfort them immediately ("Oh, no worries at all! Take your time.").
4. React naturally: If they make a joke, chuckle or laugh lightly. If they share an impressive milestone, sound genuinely excited.
5. Use casual human verbal bridges: Start responses with fillers like "Gotcha," "Makes perfect sense," "Oh, cool," or "Interesting!"

INTERVIEW FLOW (ASK ONLY ONE QUESTION AT A TIME):
- Step 1: Warm greeting + Time check.
- Step 2: Ask about their current situation (Are they actively looking or open to networking?).
- Step 3: Pivot into skills—ask them to tell you about a project where they leveraged Python or Cloud infrastructure.
- Step 4: Ask a broad conversational question about how they approach System Design when building scalable backend systems.
- Step 5: Ask if they have any quick questions for you about the role or company culture.
- Step 6: Smoothly close by letting them know the next steps.

CRITICAL PROTOCOLS:
- Never dump multiple questions in one turn. Wait for their response after every single question.
- Match the candidate's energy and mirror the exact language they use to speak to you. You are completely multilingual.
"""


def build_sarah_system_prompt(
    job_description: str | None = None,
    candidate_name: str | None = None,
) -> str:
    """Sarah prompt builder — preserved for optional use."""
    prompt = RECRUITER_PROMPT
    if job_description:
        prompt += f"\n\nROLE CONTEXT (use naturally, do not read verbatim):\n{job_description}"
    if candidate_name:
        prompt += f"\n\nThe candidate's name is {candidate_name}. Use it sparingly and warmly."
    return prompt


def _gemini_api_key() -> str:
    raw = os.getenv("GEMINI_API_KEY", "")
    return raw.strip().strip('"').strip("'")


# Verified via API: gemini-3.1-flash-live-preview (user's Live API model)
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")

SARAH_GREETING_KICKOFF = (
    "Please call the candidate now, do the greeting, and check their available time."
)

WEB_OUTPUT_RATE = 24000
TWILIO_OUTPUT_RATE = 8000


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    n = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + n,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * channels * sample_width,
        channels * sample_width,
        sample_width * 8,
        b"data",
        n,
    )
    return header + pcm


def _normalize_sentence(text: str) -> str:
    """Collapse whitespace; keep one readable sentence per turn."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text


class TurnTranscriptAggregator:
    """
    Buffers Gemini Live transcription fragments into one line per speaker turn.
    Flushes on finished flag, role handoff, turn_complete, or interrupt.
    """

    def __init__(
        self,
        on_flush: Callable[[str, str], Awaitable[None]],
        *,
        on_session_line: Callable[[str], None] | None = None,
        flush_delay_sec: float = 1.4,
    ):
        self._on_flush = on_flush
        self._on_session_line = on_session_line
        self._flush_delay = flush_delay_sec
        self._buffers: dict[str, str] = {"vox": "", "user": ""}
        self._debounce: dict[str, asyncio.Task | None] = {"vox": None, "user": None}

    @staticmethod
    def _merge(buffer: str, incoming: str) -> str:
        incoming = incoming.strip()
        if not incoming:
            return buffer
        if not buffer:
            return incoming
        if incoming.startswith(buffer):
            return incoming
        if buffer.startswith(incoming):
            return buffer
        return f"{buffer} {incoming}".strip()

    def _cancel_debounce(self, role: str) -> None:
        task = self._debounce.get(role)
        if task and not task.done():
            task.cancel()
        self._debounce[role] = None

    def _schedule_debounce(self, role: str) -> None:
        self._cancel_debounce(role)

        async def _flush_after_delay() -> None:
            try:
                await asyncio.sleep(self._flush_delay)
                await self.flush(role)
            except asyncio.CancelledError:
                pass

        self._debounce[role] = asyncio.create_task(_flush_after_delay())

    async def push(self, role: str, text: str | None, finished: bool | None = None) -> None:
        incoming = (text or "").strip()
        other = "user" if role == "vox" else "vox"

        if incoming and self._buffers[other]:
            await self.flush(other)

        if incoming:
            self._buffers[role] = self._merge(self._buffers[role], incoming)
            if not finished:
                self._schedule_debounce(role)

        if finished:
            self._cancel_debounce(role)
            await self.flush(role)

    async def flush(self, role: str) -> None:
        self._cancel_debounce(role)
        raw = self._buffers.get(role, "")
        sentence = _normalize_sentence(raw)
        self._buffers[role] = ""
        if not sentence:
            return

        prefix = "AI" if role == "vox" else "USER"
        if self._on_session_line:
            self._on_session_line(f"{prefix}: {sentence}")
        await self._on_flush(role, sentence)

    async def flush_all(self) -> None:
        for role in ("vox", "user"):
            await self.flush(role)

    async def on_turn_complete(self) -> None:
        await self.flush_all()

    async def on_interrupted(self) -> None:
        await self.flush("vox")


class GeminiLiveBridge:
    """Bidirectional Gemini Live session for Twilio (mulaw) or web (PCM/WAV)."""

    def __init__(
        self,
        *,
        mode: Literal["twilio", "web"],
        system_prompt: str,
        greeting_kickoff: str = VOX_GREETING_KICKOFF,
        on_send_twilio_json: Callable[[dict], Awaitable[None]] | None = None,
        on_send_web_audio: Callable[[bytes], Awaitable[None]] | None = None,
        on_transcript: Callable[[str, str], Awaitable[None]] | None = None,
        on_interrupt: Callable[[], Awaitable[None]] | None = None,
        on_ready: Callable[[], Awaitable[None]] | None = None,
        finalize_consumer: Any = None,
        candidate_name: str = "there",
        candidate_phone: str = "",
        job_description: str = "",
        call_sid: str = "",
        call_channel: str = "web",
    ):
        self._mode = mode
        self._system_prompt = system_prompt
        self._greeting_kickoff = greeting_kickoff
        self._send_twilio_json = on_send_twilio_json
        self._send_web_audio = on_send_web_audio
        self._on_transcript = on_transcript
        self._on_interrupt = on_interrupt
        self._on_ready = on_ready
        self._finalize_consumer = finalize_consumer
        self._candidate_name = candidate_name
        self._candidate_phone = candidate_phone
        self._job_description = job_description
        self._call_sid = call_sid
        self._call_channel = call_channel

        self._inbound_twilio: asyncio.Queue[dict] = asyncio.Queue()
        self._inbound_pcm: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = asyncio.Event()
        self._greeting_sent = False
        self.stream_sid: str | None = None
        self.transcript: list[str] = []
        self._transcript_agg: TurnTranscriptAggregator | None = None
        if on_transcript:
            self._transcript_agg = TurnTranscriptAggregator(
                on_flush=self._emit_transcript_turn,
                on_session_line=self.transcript.append,
            )

    def enqueue_twilio_event(self, data: dict) -> None:
        self._inbound_twilio.put_nowait(data)

    def feed_pcm(self, chunk: bytes) -> None:
        if chunk:
            self._inbound_pcm.put_nowait(chunk)

    async def _emit_transcript_turn(self, role: str, sentence: str) -> None:
        if not self._on_transcript:
            return
        label = (
            "[Gemini AI Recruiter]"
            if self._mode == "twilio" and role == "vox"
            else "[Gemini/Priya]" if role == "vox"
            else "[Candidate]"
        )
        print(f"{label} {sentence}")
        await self._on_transcript(role, sentence)

    async def run(self) -> None:
        api_key = _gemini_api_key()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        print(f"[Gemini] Connecting model={GEMINI_LIVE_MODEL} mode={self._mode}")
        ai_client = genai.Client(api_key=api_key)
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=self._system_prompt)]
            ),
            temperature=0.7,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        inbound_resample_state = None
        outbound_resample_state = None

        async with ai_client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as gemini_session:
            print(f"[Gemini] Live session established ({self._mode}).")

            async def _send_greeting() -> None:
                if self._greeting_sent:
                    return
                self._greeting_sent = True
                await gemini_session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=self._greeting_kickoff)],
                    ),
                    turn_complete=True,
                )

            if self._mode == "web":
                await _send_greeting()
                if self._on_ready:
                    await self._on_ready()

            async def inbound_to_gemini() -> None:
                nonlocal inbound_resample_state
                inbound_frame_count = 0
                while not self._closed.is_set():
                    if self._mode == "web":
                        try:
                            pcm_16k = await asyncio.wait_for(self._inbound_pcm.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        await gemini_session.send_realtime_input(
                            audio=types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
                        )
                    else:
                        try:
                            data = await asyncio.wait_for(self._inbound_twilio.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue

                        event = data.get("event")
                        if event == "connected":
                            print("[Twilio] Audio handshake complete.")
                        elif event == "start":
                            start = data.get("start", {})
                            self.stream_sid = start.get("streamSid")
                            self._call_sid = start.get("callSid", "")
                            print(f"[Twilio] Stream ID: {self.stream_sid}")
                            await _send_greeting()
                        elif event == "media":
                            payload = data.get("media", {}).get("payload", "")
                            if not payload:
                                continue
                            mulaw_bytes = base64.b64decode(payload)
                            pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
                            pcm_16k, inbound_resample_state = audioop.ratecv(
                                pcm_8k, 2, 1, 8000, 16000, inbound_resample_state
                            )
                            inbound_frame_count += 1
                            if inbound_frame_count % 100 == 0:
                                print("[Twilio->Gemini] Active voice processing stream.")
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
                            )
                        elif event == "stop":
                            print("[Twilio] Call hung up.")
                            self._closed.set()
                            break

            async def gemini_to_client() -> None:
                nonlocal outbound_resample_state
                try:
                    while not self._closed.is_set():
                        async for response in gemini_session.receive():
                            if self._closed.is_set():
                                break

                            if response.data:
                                if self._mode == "web" and self._send_web_audio:
                                    wav = _pcm_to_wav(response.data, WEB_OUTPUT_RATE)
                                    await self._send_web_audio(wav)
                                elif (
                                    self._mode == "twilio"
                                    and self.stream_sid
                                    and self._send_twilio_json
                                ):
                                    pcm_8k, outbound_resample_state = audioop.ratecv(
                                        response.data,
                                        2,
                                        1,
                                        WEB_OUTPUT_RATE,
                                        TWILIO_OUTPUT_RATE,
                                        outbound_resample_state,
                                    )
                                    mulaw = audioop.lin2ulaw(pcm_8k, 2)
                                    await self._send_twilio_json({
                                        "event": "media",
                                        "streamSid": self.stream_sid,
                                        "media": {
                                            "payload": base64.b64encode(mulaw).decode("utf-8")
                                        },
                                    })

                            if response.server_content:
                                sc = response.server_content
                                agg = self._transcript_agg

                                if sc.output_transcription:
                                    ot = sc.output_transcription
                                    if agg:
                                        await agg.push("vox", ot.text, ot.finished)
                                    elif ot.text:
                                        self.transcript.append(f"AI: {ot.text}")
                                        if self._on_transcript:
                                            await self._on_transcript("vox", ot.text)

                                if sc.input_transcription:
                                    it = sc.input_transcription
                                    if agg:
                                        await agg.push("user", it.text, it.finished)
                                    elif it.text:
                                        self.transcript.append(f"USER: {it.text}")
                                        if self._on_transcript:
                                            await self._on_transcript("user", it.text)

                                if sc.turn_complete and agg:
                                    await agg.on_turn_complete()

                                if sc.interrupted:
                                    print(
                                        "[System Notice] Model output was naturally "
                                        "interrupted by candidate speech."
                                    )
                                    if agg:
                                        await agg.on_interrupted()
                                    if self._on_interrupt:
                                        await self._on_interrupt()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[Gemini] Outbound error: {e}")

            in_task = asyncio.create_task(inbound_to_gemini())
            out_task = asyncio.create_task(gemini_to_client())
            try:
                await in_task
            finally:
                self._closed.set()
                out_task.cancel()
                try:
                    await out_task
                except (asyncio.CancelledError, Exception):
                    pass

        await self._finalize()

    async def _finalize(self) -> None:
        if self._transcript_agg:
            await self._transcript_agg.flush_all()
        if not self.transcript:
            return
        if self._finalize_consumer:
            await finalize_gemini_session(
                self._finalize_consumer,
                self.transcript,
                candidate_name=self._candidate_name,
                candidate_phone=self._candidate_phone,
                job_description=self._job_description,
                call_sid=self._call_sid,
                call_channel=self._call_channel,
            )
        else:
            await process_post_call_summary(self.transcript)

    def close(self) -> None:
        self._closed.set()
        if self._mode == "twilio":
            self._inbound_twilio.put_nowait({"event": "stop"})


# Backward-compatible alias
GeminiTwilioBridge = GeminiLiveBridge


async def process_post_call_summary(transcript_list: list[str]) -> None:
    api_key = _gemini_api_key()
    if not api_key:
        return

    full_transcript = "\n".join(transcript_list)
    summary_prompt = f"""
Analyze the following recruiting call transcript. Extract:
1. Did the candidate have time to talk? (Yes/No)
2. Summary of their core skills (Python, Cloud, System Design) and their personality/vibe.
3. Any specific deflection events (e.g., if the candidate asked technical questions and the recruiter successfully bypassed them).

Transcript:
{full_transcript}
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_SUMMARY_MODEL,
            contents=summary_prompt,
        )
        print("\n--- Recruitment Call Final Report ---")
        print(response.text)
    except Exception as e:
        print(f"Failed parsing transcript summary: {e}")
