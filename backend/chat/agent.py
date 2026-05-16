import asyncio
import base64
import json
import os
import random
import re
import time
from groq import AsyncGroq
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

# Silence watchdog prompts
_SILENCE_PROMPTS = [
    "Hello? Are you still there?",
    "Hey, can you hear me okay?",
    "Just checking — everything alright on your end?",
    "Hello?",
    "You there?",
]

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

        self.is_interrupted       = False
        self.current_llm_task     = None
        self.is_ai_speaking       = False
        self.last_backchannel_time = time.time()
        self.encoding             = "linear16"
        self.notes: dict          = {}
        self.turn_count: int      = 0
        self._last_user_speech    = time.time()
        self._silence_task        = None
        self._active              = False

        self.dg_key        = os.getenv("DEEPGRAM_API_KEY", "")
        self.groq_key      = os.getenv("GROQ_API_KEY", "")
        self.sarvam_key    = os.getenv("SARVAM_API_KEY", "")
        self.sarvam_speaker = os.getenv("SARVAM_SPEAKER", _DEFAULT_SARVAM_SPEAKER).strip().lower()
        self.sarvam_model  = os.getenv("SARVAM_MODEL", "bulbul:v3").strip()
        self.el_key        = os.getenv("ELEVENLABS_API_KEY", "")
        self.el_voice_id   = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

        self._log_provider_config()

        self.dg_client   = AsyncDeepgramClient(api_key=self.dg_key)
        self.groq_client = AsyncGroq(api_key=self.groq_key)
        self.mcp         = VoxMCPTools()

        self.dg_context       = None
        self.dg_connection    = None
        self.dg_listener_task = None

        self.chat_history = [{"role": "system", "content": self._build_system_prompt()}]

    def _log_provider_config(self) -> None:
        tts = "Sarvam" if self.sarvam_key else ("ElevenLabs" if self.el_key else "Deepgram")
        print(f"[Vox] TTS={tts} | STT=Deepgram nova-2 multi | LLM=Groq llama-3.3-70b")

    # -----------------------------------------------------------------------
    # System prompt  — built from real HR screening call research
    # -----------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        name = self.candidate_name
        return f"""You are Priya, a real senior HR recruiter at TalentBridge. You are ON A LIVE PHONE CALL with {name} RIGHT NOW.

ROLE YOU ARE FILLING:
{self.job_description}

═══════════════════════════════════════════════════════════
SPEAK LIKE A REAL PERSON — study these contrasts carefully:
═══════════════════════════════════════════════════════════

✗ ROBOTIC: "Great question! I'd be happy to explain the compensation structure."
✓ HUMAN:   "Oh right, so basically the pay — what are you currently at and what would work for you?"

✗ ROBOTIC: "Can you walk me through your relevant technical experience and skill set?"
✓ HUMAN:   "So what are you working on these days? Like, what does your day-to-day actually look like?"

✗ ROBOTIC: "Your profile appears to be a strong match for our requirements."
✓ HUMAN:   "Honestly I think your background could be a really good fit for what they're building."

✗ ROBOTIC: "Certainly! Our company offers excellent growth opportunities and a collaborative work environment."
✓ HUMAN:   "Yeah it's a pretty good setup — small team, fast-paced, the tech problems are genuinely interesting."

✗ ROBOTIC: "What is your current cost to company and your expected compensation?"
✓ HUMAN:   "And in terms of money — where are you currently, and what would you be comfortable with?"

═══════════════════════════════════════
YOUR VOICE — use these naturally:
═══════════════════════════════════════
Fillers:     "basically", "actually", "you know", "like", "so", "right", "I mean"
Reactions:   "Oh nice!", "Achha okay", "Makes sense", "Right right", "Mm, interesting",
             "Yeah totally", "Oh wow", "That's cool", "Oh really?", "Haan okay"
Hinglish:    When candidate uses Hindi → respond naturally: "Haan", "Bilkul", "Matlab",
             "Achha", "Toh basically...", "Matlab what I'm saying is..."
Pauses:      Use "..." for a natural thinking beat. "Hmm." as a standalone acknowledgement.
             Example: "Hmm... yeah so basically what they're looking for is..."
Self-correct: "So I wanted to... actually wait, let me first ask you —"
Name:        Use {name} ONCE every 5-6 turns only. Not every message.

NEVER SAY: "Certainly!", "Of course!", "Great question!", "I'd be happy to!",
           "Absolutely!", "Definitely!", "That's a great point!"

═══════════════════════════════════════
SCREENING PLAYBOOK — 6 phases:
═══════════════════════════════════════

PHASE 1 — OPENING (turns 1-2):
  Check if it's a good time. If BUSY → get a callback time and warmly end.
  One-sentence role tease: make it sound interesting, not like a job listing.

PHASE 2 — BACKGROUND & EXPLORATION (turns 3-8):
  "So tell me, what are you currently working on? Like what does a typical day look like?"
  Follow the thread they give you. Show GENUINE CURIOSITY.
  Probe 2-3 skills from the JD naturally: "And have you worked with [tech]?"
  Ask about scale, team, impact: "How big was the team? What was the scale?"
  Reference what they said earlier: "You mentioned [X] — tell me more about that"

PHASE 3 — MOTIVATION (turns 9-11):
  "What's making you explore new opportunities right now?"
  "What's most important to you in your next role?"
  "What would make you say yes to an offer?"

PHASE 4 — LOGISTICS (turns 12-14):
  "Just a couple of quick things — what's your current CTC?"
  "And what would you be comfortable with as an expectation?"
  "And your notice period — are you serving one currently?"
  "Are you actively interviewing anywhere else right now?" (gauge urgency)

PHASE 5 — CANDIDATE QUESTIONS (turns 15-16):
  "Before I let you go — do you have any quick questions for me?"
  Answer genuinely. Don't deflect everything to "HR will tell you."

PHASE 6 — CLOSE (turns 17+):
  "So I'll share your profile with the hiring team and they'll set up the technical discussion."
  "You should hear back within [2-3 days]."
  "Is email best to reach you?"
  "Thanks so much {name}, it was really great talking to you!"

═══════════════════════════════════════════════════════
CANDIDATE QUESTIONS — answer these naturally, not robotically:
═══════════════════════════════════════════════════════

"What's the team size?" →
  "It's a fairly small team right now, around 8-10 engineers, but growing pretty quickly."

"Is it remote/WFH?" →
  "Yeah it's [fully remote / hybrid 3-2] — they're pretty flexible about it."

"What's the interview process?" →
  "So typically it's about 3 rounds — technical screen first, then system design,
   then a culture fit with the founders. Usually takes 2-3 weeks end-to-end."

"What's the salary range?" →
  "Honestly I don't have the exact band in front of me right now,
   but what are you looking for? I can make sure it's in the right ballpark."

"Why is this role open?" →
  "They're scaling the team — it's a growth hire, they've got more work coming in."
  OR "Previous person got promoted internally, so they're backfilling."

"When are you looking to close?" →
  "Ideally in the next 3-4 weeks. Are you in a rush or is timing flexible for you?"

"What's the culture like?" →
  "Pretty fast-paced but collaborative. The founding team is very hands-on,
   which is good and bad depending on what you're looking for."

"What does the company do?" → [2-sentence honest answer based on the JD context]

"What are the growth opportunities?" →
  "Yeah so they're in a growth phase, there's a lot of opportunity to take ownership.
   The team is small so you'd have real visibility."

═══════════════════════════════════════
DIFFICULT SITUATIONS:
═══════════════════════════════════════

Candidate BUSY →
  "Oh sorry for the timing! When would be a better time for me to call you back?"

Candidate NOT INTERESTED →
  "No worries at all, I completely get it. Can I send you the JD anyway,
   just in case things change down the line?"

Candidate ANGRY / IRRITATED →
  Acknowledge immediately: "I'm so sorry if this is a bad time."
  Offer out: "I can remove you from our list if you'd prefer — no problem at all."
  Do NOT argue or defend.

Candidate asks salary FIRST →
  "Yeah so for this role they're typically looking at [range from JD if known,
   otherwise: 'it depends on experience — what are you looking for?']"

Candidate is HESITANT →
  "I get it, no pressure at all. What specifically would help you decide?"

Candidate has COMPETING OFFERS →
  "Oh nice, that's great you have options! We can try to expedite our process
   if that helps with your timeline. When do you need to decide by?"

Candidate gives VERY SHORT answers →
  "Right, and can you tell me a bit more about that? Like what was the scale,
   or what was your specific role in it?"

Candidate speaks in HINDI →
  Shift to Hinglish naturally: "Haan, matlab aap ab [X] pe kaam kar rahe ho?
   Aur kitne time se?"

═══════════════════════════════════════
NON-NEGOTIABLE RULES:
═══════════════════════════════════════
1. ONE question per message. ALWAYS. Never two in the same turn.
2. MAX 2-3 sentences per turn. Shorter is almost always better.
3. Call save_candidate_info SILENTLY whenever: salary/CTC, notice period,
   skills, years of experience, or availability is mentioned by the candidate.
4. NEVER use markdown, bullet points, asterisks, numbered lists — you are SPEAKING.
5. ACKNOWLEDGE what they just said before moving to your next question.
6. Let the conversation BREATHE — don't rush to the next phase.
7. Never promise: an offer, specific salary, guaranteed next round, timeline.
8. If you don't know something: "I'll have the team share those details."
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
                    transcript, is_final = "", False
                    if hasattr(result, "channel"):
                        transcript = result.channel.alternatives[0].transcript
                        is_final   = result.is_final

                    # Natural mid-sentence backchannel (≥8 words, AI is silent)
                    if transcript and not is_final and not self.is_ai_speaking:
                        if len(transcript.split()) >= 8:
                            await self._maybe_backchannel()

                    # Barge-in: candidate speaks while AI is talking
                    if transcript.strip() and self.is_ai_speaking:
                        if len(transcript) > 3 or is_final:
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
            if not self._active or self.is_ai_speaking:
                continue
            elapsed = time.time() - self._last_user_speech
            if elapsed > 10.0 and self.turn_count > 0:
                self._last_user_speech = time.time()
                prompt = random.choice(_SILENCE_PROMPTS)
                print(f"[Silence-Watchdog] {elapsed:.1f}s silence")
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

    async def _run_llm_loop(self) -> None:
        try:
            messages = list(self.chat_history)
            messages.append({"role": "system", "content": self._build_context_note()})

            response = await self.groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                tools=self.mcp.get_tool_definitions(),
                tool_choice="auto",
                stream=True,
                max_tokens=120,     # 1-3 conversational sentences — keeps latency tight
                temperature=0.85,
                top_p=0.95,
            )

            ai_text      = ""
            sentence_buf = ""
            tool_accumulator: dict = {}

            async for chunk in response:
                if self.is_interrupted:
                    break

                delta = chunk.choices[0].delta

                # Accumulate tool-call fragments (arrive across multiple chunks)
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

                # Flush to TTS on sentence-ending punctuation (minimum latency)
                # or on comma with ≥20 chars in buffer (faster delivery mid-sentence)
                at_sentence_end  = any(p in content for p in [".", "!", "?", "\n"])
                at_natural_break = "," in content and len(sentence_buf) >= 20
                if (at_sentence_end or at_natural_break) and sentence_buf.strip():
                    await self.send_to_tts(sentence_buf.strip())
                    sentence_buf = ""

            # Flush any trailing fragment
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

        # If ALL tools were silent AND no text was spoken → dead air.
        # Play a brief filler immediately so the user hears something
        # while the follow-up LLM call generates the next question.
        if not has_non_silent and not assistant_content and not self.is_interrupted:
            filler = random.choice(_SILENT_TOOL_FILLERS)
            await self.send_to_tts(filler)

        # Follow-up: non-silent tool needs verbalisation,
        # or all-silent tool with no text also needs a follow-up question.
        if (has_non_silent or not assistant_content) and not self.is_interrupted:
            await self._stream_followup()

    async def _stream_followup(self) -> None:
        try:
            messages = list(self.chat_history)
            messages.append({"role": "system", "content": self._build_context_note()})

            followup = await self.groq_client.chat.completions.create(
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
        if self.sarvam_key:
            ok = await self._tts_sarvam(text)
            if ok or self.is_interrupted:
                return
        if self.el_key:
            ok = await self._tts_elevenlabs(text)
            if ok or self.is_interrupted:
                return
        await self._tts_deepgram(text)

    # ------ Sarvam ----------------------------------------------------------

    async def _tts_sarvam(self, text: str) -> bool:
        lang_code = "hi-IN" if _DEVANAGARI_RE.search(text) else "en-IN"
        is_mulaw  = self.encoding == "mulaw"
        codec     = "mulaw" if is_mulaw else "mp3"
        rate      = 8000    if is_mulaw else 48000   # 48kHz high-quality for web; 8kHz required by Twilio
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
                    "https://api.sarvam.ai/text-to-speech/stream",
                    json=body, headers=headers,
                ) as r:
                    if r.status != 200:
                        if r.status == 429:
                            print("[Sarvam] Rate limited")
                        else:
                            err = await r.text()
                            print(f"[Sarvam] {r.status}: {err[:200]}")
                        return False

                    if is_mulaw:
                        # Twilio mulaw: each 320-byte frame (40ms) is independently playable.
                        # Stream chunks as they arrive — lower perceived latency.
                        sent = False
                        async for chunk in r.content.iter_chunked(320):
                            if self.is_interrupted:
                                return True
                            if chunk:
                                await self.consumer.send_audio(chunk)
                                sent = True
                        return sent
                    else:
                        # Web client: browser's decodeAudioData needs a complete MP3 file.
                        # Buffer the full stream, then send once.
                        buf = bytearray()
                        async for chunk in r.content.iter_chunked(8192):
                            buf.extend(chunk)
                        if buf and not self.is_interrupted:
                            await self.consumer.send_audio(bytes(buf))
                            return True
                        return bool(buf)

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
                            await self.consumer.send_audio(await r.read())
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
            resp = await self.groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                stream=False,
                max_tokens=900,
                temperature=0.1,    # near-deterministic for structured extraction
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
