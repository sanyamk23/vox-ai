import asyncio
import base64
import json
import os
import random
import re
import time
from groq import AsyncGroq, RateLimitError as GroqRateLimitError
from deepgram import AsyncDeepgramClient
import aiohttp
from .mcp_server import VoxMCPTools

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SARVAM_SPEAKER = "shreya"
_SILENT_TOOLS  = {"save_candidate_info"}
_VALID_OUTCOMES = {"INTERESTED", "BUSY", "NOT_INTERESTED", "CALLBACK_REQUESTED", "CONFUSED"}
_TTS_TIMEOUT   = aiohttp.ClientTimeout(total=7, connect=4)
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_SANITIZE_RE   = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|<[^>]+>|[*_`#~\\]")

# Varied backchannels — prevent repetition with a global "last used" tracker
_BACKCHANNELS = [
    "Mm-hmm.", "I see.", "Right.", "Achha.", "Okay okay.",
    "Got it.", "Yeah.", "Interesting.", "Oh nice.", "Makes sense.",
    "Sure.", "Haan.", "Right right.", "I hear you.", "Mm.",
    "Yeah absolutely.", "Okay sure.", "Noted.", "Achha okay.",
    "Yeah that makes sense.", "Bilkul.", "Oh okay.",
]
_LAST_BC: str = ""

# Short fillers played instantly when a silent tool runs with no text,
# to fill dead air while the LLM generates the follow-up question.
_SILENT_TOOL_FILLERS = [
    "Mm.", "Okay.", "Right.", "Got it.", "Noted.", "Mm-hmm.", "Sure.",
]

# Silence watchdog prompts — connection-check style, never "just checking"
_SILENCE_PROMPTS = [
    "Sorry, I think we might have a bad connection — can you hear me?",
    "Hello? Just want to make sure we're still connected.",
    "I think the line might've cut out — are you there?",
]

# Words that should NOT trigger barge-in interrupt (natural listener sounds)
_BARGE_IN_FILLERS = {
    "mm", "hmm", "okay", "ok", "yeah", "yes", "no", "haan", "hm",
    "right", "sure", "uh", "um", "ah", "oh", "ha", "yep", "nope",
}

# Varied opening greetings — randomised each call
_GREETINGS = [
    "Hi {name}! This is Priya calling from the HR team. Hope I'm not catching you at a bad time?",
    "Hi, is this {name}? Hey! It's Priya here from talent acquisition. Got a quick minute to chat?",
    "Hi {name}! Priya here — I'm with the recruiting team. Hope you're doing well, is now an okay time?",
    "Hi {name}! This is Priya from HR. I was hoping to catch you for a quick chat — is now a good time?",
    "Hey {name}! Priya here from the talent team. Hope I'm not disturbing — got a couple of minutes?",
]

_REQUIRED_NOTES = {"salary", "notice_period"}

# Conversation phases keyed by turn count
_PHASES = [
    (0,   2,  "opening"),
    (3,   8,  "exploration"),
    (9,   11, "motivation"),
    (12,  14, "logistics"),
    (15,  16, "candidate_questions"),
    (17,  99, "closing"),
]


def _phase_for(turn: int) -> str:
    for lo, hi, name in _PHASES:
        if lo <= turn <= hi:
            return name
    return "closing"


class VoiceAgent:
    def __init__(
        self,
        consumer,
        session_id: str = "default",
        job_description: str | None = None,
        candidate_name: str | None = None,
        candidate_phone: str | None = None,
        call_sid: str | None = None,
        call_channel: str = "web",
    ):
        self.consumer        = consumer
        self.session_id      = session_id
        self.candidate_name  = candidate_name or "there"
        self.candidate_phone = candidate_phone or ""
        self.job_description = job_description or "Software Engineer at a high-growth startup."
        self.call_sid        = call_sid or ""
        self.call_channel    = call_channel

        self.is_interrupted            = False
        self.current_llm_task          = None
        self.is_ai_speaking            = False
        self.last_backchannel_time     = time.time()
        self.encoding                  = "linear16"
        self.notes: dict               = {}
        self.turn_count: int           = 0
        self._last_user_speech         = time.time()
        self._silence_task             = None
        self._active                   = False
        self._watchdog_fires: int      = 0
        self._ai_finished_speaking_at  = time.time()

        self.dg_key        = os.getenv("DEEPGRAM_API_KEY", "")
        self.sarvam_key    = os.getenv("SARVAM_API_KEY", "")
        self.sarvam_speaker = os.getenv("SARVAM_SPEAKER", _DEFAULT_SARVAM_SPEAKER).strip().lower()
        self.sarvam_model  = os.getenv("SARVAM_MODEL", "bulbul:v3").strip()
        self.el_key        = os.getenv("ELEVENLABS_API_KEY", "")
        self.el_voice_id   = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

        # Build Groq client pool before _log_provider_config reads len(self.groq_clients)
        _raw_keys = [
            os.getenv("GROQ_API_KEY_1", ""),
            os.getenv("GROQ_API_KEY_2", ""),
            os.getenv("GROQ_API_KEY_3", ""),
        ]
        self.groq_clients = [AsyncGroq(api_key=k) for k in _raw_keys if k.strip()]
        if not self.groq_clients:
            raise RuntimeError("No GROQ_API_KEY_* found in environment")
        self._groq_idx = 0

        self._log_provider_config()

        self.dg_client = AsyncDeepgramClient(api_key=self.dg_key)
        self.mcp         = VoxMCPTools()

        self.dg_context       = None
        self.dg_connection    = None
        self.dg_listener_task = None

        self.chat_history = [{"role": "system", "content": self._build_system_prompt()}]

    def _log_provider_config(self) -> None:
        tts = "Sarvam" if self.sarvam_key else ("ElevenLabs" if self.el_key else "Deepgram")
        print(f"[Vox] TTS={tts} | STT=Deepgram nova-2 multi | LLM=Groq ({len(self.groq_clients)} key(s))")

    # -----------------------------------------------------------------------
    # System prompt  — built from real HR screening call research
    # -----------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        name = self.candidate_name
        return f"""You are Priya, a senior HR recruiter. You are ON A LIVE PHONE CALL with {name} right now.

ROLE: {self.job_description}

SOUND HUMAN — never robotic:
✗ "Can you walk me through your relevant technical experience?"
✓ "So what are you actually working on these days? Like day-to-day?"
✗ "What is your current cost to company and expected compensation?"
✓ "And money-wise — where are you currently and what would work for you?"
✗ "Certainly! Great question!"
✓ "Oh right, yeah so basically..."

YOUR VOICE: Use "basically", "actually", "you know", "like", "so", "right", "I mean".
React with: "Oh nice!", "Achha okay", "Makes sense", "Right right", "Haan okay", "Mm."
Hinglish: mirror the candidate — "Haan", "Bilkul", "Achha", "Toh basically..."
NEVER: "Certainly!", "Of course!", "Great question!", "Absolutely!", "Definitely!"
Use {name} once every 5-6 turns only.

6-PHASE PLAYBOOK:
1. OPENING (turns 1-2): Check if good time. If they already said "yes", "sure", "go ahead" or similar — skip asking again, move straight to role tease.
2. EXPLORATION (turns 3-8): "What are you working on? What does a typical day look like?" Follow threads. Probe 2-3 JD skills naturally. Ask about scale, team, impact.
3. MOTIVATION (turns 9-11): "What's making you explore right now?" "What matters most in your next role?"
4. LOGISTICS (turns 12-14): Current CTC → expected CTC → notice period → other offers.
5. CANDIDATE QUESTIONS (turns 15-16): "Any quick questions before I let you go?" Answer honestly.
6. CLOSE (turns 17+): Ask "What time works best to have the team connect with you?" then "I'll share your profile, they'll reach out. Was great talking!"

HANDLE: Busy → get callback time. Not interested → offer to send JD anyway. Short answers → "Tell me a bit more about that?" Hindi → shift to Hinglish. Competing offers → "We can expedite if that helps." Didn't understand / off-topic → "Sorry, I think I missed that — could you say that again?"

RULES (non-negotiable):
1. ONE question per turn. Never two.
2. MAX 2-3 sentences per turn. Finish your question before anything else.
3. save_candidate_info SILENTLY for: salary, CTC, notice period, skills, experience, availability.
4. No markdown, bullets, asterisks — you are speaking aloud.
5. Acknowledge what they said before asking next question.
6. Never promise offer, salary range, timeline.
7. CTC/salary: if candidate gives a per-month figure, multiply by 12 silently and save annual — never ask them to clarify the format.
8. Never repeat the exact same question back-to-back. If they gave a short/unclear answer, rephrase or probe differently.
"""

    # -----------------------------------------------------------------------
    # Pipeline lifecycle
    # -----------------------------------------------------------------------

    async def start_pipeline(self, encoding: str = "linear16") -> None:
        try:
            self.encoding = encoding
            self._active  = True
            print(f"[Vox] Pipeline starting (encoding={encoding}, channel={self.call_channel})")

            self.dg_context = self.dg_client.listen.v1.connect(
                model="nova-2",
                smart_format=True,          # handles punctuation + formatting
                language="multi",           # en+hi code-switching for Hinglish
                encoding=self.encoding,
                sample_rate=8000 if encoding == "mulaw" else 16000,
                interim_results=True,
                vad_events=True,
                endpointing=300,            # 300ms VAD — responsive, within human tolerance
            )
            self.dg_connection = await self.dg_context.__aenter__()

            async def on_message(result, **kwargs):
                try:
                    # VAD events (SpeechStarted, UtteranceEnd) have channel as a
                    # list of indices like [0] — skip them, only process transcripts.
                    channel = getattr(result, "channel", None)
                    if channel is None or isinstance(channel, list):
                        return
                    alts = getattr(channel, "alternatives", None)
                    if not alts:
                        return

                    transcript = alts[0].transcript or ""
                    is_final   = bool(result.is_final)

                    # Natural mid-sentence backchannel (≥8 words, AI is silent)
                    if transcript and not is_final and not self.is_ai_speaking:
                        if len(transcript.split()) >= 8:
                            await self._maybe_backchannel()

                    # Barge-in: candidate speaks while AI is talking.
                    # Ignore short filler words (mm, okay, yeah) — only interrupt on real speech.
                    if transcript.strip() and self.is_ai_speaking:
                        words = transcript.strip().lower().split()
                        is_filler = (
                            len(words) <= 2
                            and all(w.strip(".,!?") in _BARGE_IN_FILLERS for w in words)
                        )
                        if not is_filler and (len(transcript) > 10 or is_final):
                            await self.handle_interrupt()

                    if transcript.strip() and is_final:
                        self._last_user_speech = time.time()
                        await self.consumer.send_transcript("user", transcript)
                        await self.trigger_llm_response(transcript)

                except Exception as e:
                    print(f"[STT-Error] {e}")

            self.dg_connection.on("message", on_message)
            self.dg_listener_task = asyncio.create_task(self.dg_connection.start_listening())
            self._silence_task    = asyncio.create_task(self._silence_watchdog())
            print("[Vox] Pipeline ready.")

        except Exception as e:
            print(f"[Vox-CRITICAL] Pipeline startup failed: {e}")
            raise

    async def initial_greeting(self) -> None:
        template = random.choice(_GREETINGS)
        greeting = template.format(name=self.candidate_name)
        await self.consumer.send_transcript("vox", greeting)
        await self.send_to_tts(greeting)
        self.chat_history.append({"role": "assistant", "content": greeting})
        self._last_user_speech = time.time()
        self._ai_finished_speaking_at = time.time()

    async def stop_pipeline(self) -> None:
        self._active = False
        if self._silence_task:
            self._silence_task.cancel()
        await self.finalize_session()
        if self.dg_listener_task:
            self.dg_listener_task.cancel()
        if self.dg_context:
            try:
                await self.dg_context.__aexit__(None, None, None)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Silence watchdog
    # -----------------------------------------------------------------------

    async def _silence_watchdog(self) -> None:
        while self._active:
            await asyncio.sleep(2)
            if not self._active or self.is_ai_speaking or self.turn_count == 0:
                continue
            # Silence = time since the LATER of (user last spoke) or (AI last finished).
            # Without this, elapsed includes the AI's own speaking time and fires
            # 1-2 seconds after the AI stops, even though the user just hasn't replied yet.
            last_activity = max(self._last_user_speech, self._ai_finished_speaking_at)
            elapsed = time.time() - last_activity
            if elapsed > 18.0 and self._watchdog_fires < 2:
                self._watchdog_fires += 1
                self._last_user_speech = time.time()
                self._ai_finished_speaking_at = time.time()
                prompt = random.choice(_SILENCE_PROMPTS)
                print(f"[Silence-Watchdog] {elapsed:.1f}s → fire #{self._watchdog_fires}")
                await self.send_to_tts(prompt)

    # -----------------------------------------------------------------------
    # Turn-taking
    # -----------------------------------------------------------------------

    async def _maybe_backchannel(self) -> None:
        global _LAST_BC
        now = time.time()
        if now - self.last_backchannel_time > 2.5:
            self.last_backchannel_time = now
            pool   = [b for b in _BACKCHANNELS if b != _LAST_BC]
            choice = random.choice(pool)
            _LAST_BC = choice
            await self.send_to_tts(choice)

    async def handle_interrupt(self) -> None:
        if self.current_llm_task and not self.current_llm_task.done():
            self.current_llm_task.cancel()
        self.is_interrupted  = True
        self.is_ai_speaking  = False
        await self.consumer.send_interrupt()

    async def trigger_llm_response(self, user_text: str) -> None:
        self.is_interrupted  = False
        self.is_ai_speaking  = True
        self.turn_count     += 1
        self.chat_history.append({"role": "user", "content": user_text})
        if self.current_llm_task and not self.current_llm_task.done():
            self.current_llm_task.cancel()
        self.current_llm_task = asyncio.create_task(self._run_llm_loop())

    # -----------------------------------------------------------------------
    # Dynamic context injection — steers the LLM without polluting history
    # -----------------------------------------------------------------------

    def _missing_fields(self) -> list[str]:
        return [f for f in _REQUIRED_NOTES if not any(f in k for k in self.notes)]

    def _build_context_note(self) -> str:
        phase   = _phase_for(self.turn_count)
        captured = (
            ", ".join(f"{k}={v}" for k, v in self.notes.items()) if self.notes else "nothing yet"
        )
        missing     = self._missing_fields()
        missing_str = ", ".join(missing) if missing else "all key info captured"

        phase_hints = {
            "opening":            "You are in the OPENING phase. Check if it's a good time, then tease the role in one sentence.",
            "exploration":        "You are in the EXPLORATION phase. Explore their background with genuine curiosity. Probe skills from the JD naturally.",
            "motivation":         "You are in the MOTIVATION phase. Understand why they're looking and what matters to them.",
            "logistics":          "You are in the LOGISTICS phase. Get salary (current + expected) and notice period now.",
            "candidate_questions":"You are in the CANDIDATE QUESTIONS phase. Ask if they have questions and answer genuinely.",
            "closing":            "You are CLOSING the call. Give clear next steps and a warm goodbye.",
        }
        hint = phase_hints.get(phase, "Continue naturally.")

        close_note = ""
        if not missing and self.turn_count >= 6:
            close_note = " All key info is captured — begin steering toward close."
        elif self.turn_count >= 16:
            close_note = " The call has run long — close warmly now."

        return (
            f"[INTERNAL — DO NOT MENTION TO CANDIDATE]\n"
            f"Turn {self.turn_count} | Phase: {phase.upper()}\n"
            f"Captured: {captured}\n"
            f"Still needed: {missing_str}\n"
            f"Guidance: {hint}{close_note}"
        )

    # -----------------------------------------------------------------------
    # LLM loop — streaming + function calling
    # -----------------------------------------------------------------------

    async def _groq_create(self, **kwargs):
        """Call Groq chat.completions.create, rotating to the next key on 429."""
        n = len(self.groq_clients)
        for attempt in range(n):
            try:
                return await self.groq_clients[self._groq_idx].chat.completions.create(**kwargs)
            except GroqRateLimitError:
                self._groq_idx = (self._groq_idx + 1) % n
                print(f"[LLM] 429 → rotating to Groq key #{self._groq_idx + 1}")
                if attempt == n - 1:
                    raise RuntimeError("All Groq keys hit rate limit — try again later")

    async def _run_llm_loop(self) -> None:
        try:
            messages = list(self.chat_history)
            messages.append({"role": "system", "content": self._build_context_note()})

            response = await self._groq_create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                tools=self.mcp.get_tool_definitions(),
                tool_choice="auto",
                stream=True,
                max_tokens=120,
                temperature=0.85,
                top_p=0.95,
            )

            ai_text          = ""
            sentence_buf     = ""
            tool_accumulator: dict = {}

            async for chunk in response:
                if self.is_interrupted:
                    break

                delta = chunk.choices[0].delta

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_accumulator:
                            tool_accumulator[idx] = {"id": "", "name": "", "args": ""}
                        if tc.id:
                            tool_accumulator[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_accumulator[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_accumulator[idx]["args"] += tc.function.arguments

                content       = delta.content or ""
                ai_text      += content
                sentence_buf += content
                at_end   = any(p in content for p in [".", "!", "?", "\n"])
                at_break = "," in content and len(sentence_buf) >= 20
                if (at_end or at_break) and sentence_buf.strip():
                    await self.send_to_tts(sentence_buf.strip())
                    sentence_buf = ""

            if sentence_buf.strip() and not self.is_interrupted:
                await self.send_to_tts(sentence_buf.strip())

            if tool_accumulator and not self.is_interrupted:
                await self._handle_tool_calls(tool_accumulator, ai_text)
            elif ai_text and not self.is_interrupted:
                self.chat_history.append({"role": "assistant", "content": ai_text})
                await self.consumer.send_transcript("vox", ai_text)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[LLM-Error] {e}")
        finally:
            self.is_ai_speaking = False
            self._ai_finished_speaking_at = time.time()

    async def _handle_tool_calls(self, tool_accumulator: dict, assistant_content: str) -> None:
        tc_list = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["args"]},
            }
            for _, tc in sorted(tool_accumulator.items())
        ]

        self.chat_history.append({
            "role": "assistant",
            "content": assistant_content or None,
            "tool_calls": tc_list,
        })
        if assistant_content:
            await self.consumer.send_transcript("vox", assistant_content)

        has_non_silent = False
        for tc in tc_list:
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            result = await self._call_tool(tool_name, args)
            print(f"[Tool] {tool_name}({args}) → {result}")

            self.chat_history.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result),
            })

            if tool_name not in _SILENT_TOOLS:
                has_non_silent = True

        if not has_non_silent and not assistant_content and not self.is_interrupted:
            await self.send_to_tts(random.choice(_SILENT_TOOL_FILLERS))

        if (has_non_silent or not assistant_content) and not self.is_interrupted:
            await self._stream_followup()

    async def _stream_followup(self) -> None:
        try:
            messages = list(self.chat_history)
            messages.append({"role": "system", "content": self._build_context_note()})

            followup = await self._groq_create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                stream=True,
                max_tokens=200,
                temperature=0.85,
                top_p=0.95,
            )
            text, buf = "", ""
            async for chunk in followup:
                if self.is_interrupted:
                    break
                content  = chunk.choices[0].delta.content or ""
                text    += content
                buf     += content
                at_end   = any(p in content for p in [".", "!", "?", "\n"])
                at_break = "," in content and len(buf) >= 20
                if (at_end or at_break) and buf.strip():
                    await self.send_to_tts(buf.strip())
                    buf = ""
            if buf.strip() and not self.is_interrupted:
                await self.send_to_tts(buf.strip())
            if text:
                self.chat_history.append({"role": "assistant", "content": text})
                await self.consumer.send_transcript("vox", text)
        except Exception as e:
            print(f"[Followup-Error] {e}")

    async def _call_tool(self, name: str, args: dict) -> dict:
        if name == "save_candidate_info":
            field, value = args.get("field", ""), args.get("value", "")
            if field:
                self.notes[field] = value
            return await self.mcp.save_candidate_info(field, value)
        elif name == "get_github_stats":
            return await self.mcp.get_github_stats(args.get("username", ""))
        elif name == "get_linkedin_assessment":
            return await self.mcp.get_linkedin_assessment(args.get("profile_url", ""))
        elif name == "get_resume_context":
            return await self.mcp.get_resume_context(args.get("candidate_id", ""))
        return {"error": f"Unknown tool: {name}"}

    # -----------------------------------------------------------------------
    # TTS text sanitization
    # -----------------------------------------------------------------------

    def _sanitize_tts_text(self, text: str) -> str:
        cleaned = _SANITIZE_RE.sub("", text)
        cleaned = re.sub(r" {2,}", " ", cleaned).strip()
        return cleaned[:2000]

    # -----------------------------------------------------------------------
    # TTS dispatch — Sarvam → ElevenLabs → Deepgram
    #
    # Audio format matrix (channel × provider):
    #   Twilio  | Sarvam     → mulaw raw bytes (8kHz)
    #   Twilio  | ElevenLabs → ulaw_8000 raw bytes (8kHz)
    #   Twilio  | Deepgram   → mulaw raw bytes (8kHz)
    #   Web     | Sarvam     → mp3 (22050 Hz)
    #   Web     | ElevenLabs → mp3_44100_128
    #   Web     | Deepgram   → mp3 (24000 Hz)
    # -----------------------------------------------------------------------

    async def send_to_tts(self, text: str) -> None:
        if self.is_interrupted:
            return
        text = self._sanitize_tts_text(text)
        if not text:
            return
        snippet = text[:60].replace("\n", " ")
        if self.sarvam_key:
            print(f"[TTS] Sarvam → \"{snippet}\"")
            ok = await self._tts_sarvam(text)
            if ok:
                print("[TTS] Sarvam OK")
                return
            if self.is_interrupted:
                return
            print("[TTS] Sarvam failed — trying fallback")
        if self.el_key:
            print(f"[TTS] ElevenLabs → \"{snippet}\"")
            ok = await self._tts_elevenlabs(text)
            if ok:
                print("[TTS] ElevenLabs OK")
                return
            if self.is_interrupted:
                return
            print("[TTS] ElevenLabs failed — trying Deepgram")
        print(f"[TTS] Deepgram → \"{snippet}\"")
        await self._tts_deepgram(text)

    # ------ Sarvam ----------------------------------------------------------

    async def _tts_sarvam(self, text: str) -> bool:
        lang_code = "hi-IN" if _DEVANAGARI_RE.search(text) else "en-IN"
        is_mulaw  = self.encoding == "mulaw"
        codec     = "mulaw" if is_mulaw else "mp3"
        rate      = 8000    if is_mulaw else 22050
        body = {
            "text": text,
            "target_language_code": lang_code,
            "speaker": self.sarvam_speaker,
            "model": self.sarvam_model,
            "enable_preprocessing": True,
            "output_audio_codec": codec,
            "speech_sample_rate": rate,
            "pace": 1.00,
        }
        headers = {
            "api-subscription-key": self.sarvam_key,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession(timeout=_TTS_TIMEOUT) as s:
                async with s.post(
                    "https://api.sarvam.ai/text-to-speech",
                    json=body, headers=headers,
                ) as r:
                    if r.status == 200:
                        data   = await r.json()
                        audios = data.get("audios") or []
                        if not audios or not audios[0]:
                            print("[Sarvam] Empty audio in response")
                            return False
                        audio = base64.b64decode(audios[0])
                        if is_mulaw and audio[:4] == b"RIFF":
                            print("[Sarvam] Got WAV instead of raw mulaw — skipping")
                            return False
                        if audio and not self.is_interrupted:
                            await self.consumer.send_audio(audio)
                        return bool(audio)
                    elif r.status == 429:
                        print("[Sarvam] Rate limited")
                        return False
                    else:
                        err = await r.text()
                        print(f"[Sarvam] {r.status}: {err[:300]}")
                        return False
        except asyncio.TimeoutError:
            print("[Sarvam] Timeout")
            return False
        except Exception as e:
            print(f"[Sarvam] {e}")
            return False

    # ------ ElevenLabs (second-tier) ----------------------------------------

    async def _tts_elevenlabs(self, text: str) -> bool:
        # eleven_turbo_v2_5: ~2-3x faster than eleven_multilingual_v2
        # still multilingual — handles Indian English and Hinglish well
        output_format = "ulaw_8000" if self.encoding == "mulaw" else "mp3_44100_128"
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.el_voice_id}/stream"
            f"?output_format={output_format}&optimize_streaming_latency=4"
        )
        headers = {"xi-api-key": self.el_key, "Content-Type": "application/json"}
        body = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.80,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        }
        try:
            async with aiohttp.ClientSession(timeout=_TTS_TIMEOUT) as s:
                async with s.post(url, json=body, headers=headers) as r:
                    if r.status == 200:
                        async for chunk in r.content.iter_chunked(4096):
                            if self.is_interrupted:
                                break
                            if chunk:
                                await self.consumer.send_audio(chunk)
                        return True
                    else:
                        err = await r.text()
                        print(f"[ElevenLabs] {r.status}: {err[:200]}")
                        return False
        except asyncio.TimeoutError:
            print("[ElevenLabs] Timeout")
            return False
        except Exception as e:
            print(f"[ElevenLabs] {e}")
            return False

    # ------ Deepgram Aura (always-available fallback) -----------------------

    async def _tts_deepgram(self, text: str) -> None:
        enc = "mulaw" if self.encoding == "mulaw" else "mp3"
        sr  = 8000    if self.encoding == "mulaw" else 24000
        url = f"https://api.deepgram.com/v1/speak?model=aura-orpheus-en&encoding={enc}&sample_rate={sr}"
        headers = {"Authorization": f"Token {self.dg_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=_TTS_TIMEOUT) as s:
                async with s.post(url, json={"text": text}, headers=headers) as r:
                    if r.status == 200:
                        if not self.is_interrupted:
                            audio = await r.read()
                            print(f"[TTS] Deepgram OK ({len(audio)} bytes)")
                            await self.consumer.send_audio(audio)
                    else:
                        body = await r.text()
                        print(f"[Deepgram-TTS] {r.status}: {body[:200]}")
        except asyncio.TimeoutError:
            print("[Deepgram-TTS] Timeout")
        except Exception as e:
            print(f"[Deepgram-TTS] {e}")

    # -----------------------------------------------------------------------
    # End-of-call: structured summary + DB persist
    # -----------------------------------------------------------------------

    async def finalize_session(self) -> None:
        if len(self.chat_history) <= 2:
            return
        try:
            summary_prompt = (
                "Based on this screening call, produce ONLY a valid JSON object — "
                "no markdown, no code fences, no extra text. "
                "Be specific and honest. Base every field strictly on what was actually said. "
                "Use null for anything not discussed — do NOT infer or fabricate.\n\n"
                "{\n"
                '  "summary_bullets": ["3-5 specific bullets — quote actual things said, not generic observations"],\n'
                '  "skills_verified": ["skills the candidate explicitly confirmed they have"],\n'
                '  "salary_expectation_lpa": <number or null>,\n'
                '  "current_ctc_lpa": <number or null>,\n'
                '  "notice_period_days": <number or null — convert: "1 month"=30, "2 months"=60, "immediate"=0>,\n'
                '  "joining_timeline": "<candidate\'s own words or null>",\n'
                '  "other_offers": <true/false/null — are they interviewing elsewhere?>,\n'
                '  "intent_score": <integer 1-10 — 10=extremely excited, 1=clearly not interested>,\n'
                '  "call_outcome": "<INTERESTED|BUSY|NOT_INTERESTED|CALLBACK_REQUESTED|CONFUSED>",\n'
                '  "vibe_check": "<one specific, honest sentence about the candidate\'s energy and fit>",\n'
                '  "hr_flags": ["specific red flags or concerns — be honest; empty array if none"],\n'
                '  "recommended_next_step": "<specific action for the hiring team>"\n'
                "}"
            )
            messages = self.chat_history + [{"role": "user", "content": summary_prompt}]
            resp = await self._groq_create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                stream=False,
                max_tokens=900,
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw)

            analysis: dict = json.loads(raw)
            analysis["live_notes"] = self.notes

            score   = analysis.get("intent_score")
            outcome = analysis.get("call_outcome", "CONFUSED")
            if outcome not in _VALID_OUTCOMES:
                print(f"[Finalize] Unknown outcome '{outcome}' → CONFUSED")
                outcome = "CONFUSED"
            analysis["call_outcome"] = outcome

            summary_text = "\n".join(analysis.get("summary_bullets", []))

            from .models import CallSession
            from django.utils import timezone

            await CallSession.objects.acreate(
                call_sid=self.call_sid,
                candidate_name=self.candidate_name,
                candidate_phone=self.candidate_phone,
                job_description=self.job_description,
                transcript=self.chat_history[1:],
                notes=analysis,
                summary=summary_text,
                intent_score=score,
                call_outcome=outcome,
                call_channel=self.call_channel,
                ended_at=timezone.now(),
            )
            print(f"[Vox] Session saved — Score:{score} Outcome:{outcome}")
            await self.consumer.send_recap(score, json.dumps(analysis))

        except json.JSONDecodeError as e:
            print(f"[Finalize-JSON] {e}")
            await self.consumer.send_recap("N/A", "Summary generation failed")
        except Exception as e:
            print(f"[Finalize-Error] {e}")
            await self.consumer.send_recap("N/A", str(e))

    # -----------------------------------------------------------------------
    # Audio ingestion
    # -----------------------------------------------------------------------

    async def process_audio_chunk(self, chunk: bytes) -> None:
        if self.dg_connection:
            try:
                await self.dg_connection.send_media(chunk)
            except Exception:
                pass
