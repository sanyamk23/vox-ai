import asyncio
import os
import json
import aiohttp
import re
import time
import random
from opentelemetry import trace
from groq import AsyncGroq
from deepgram import AsyncDeepgramClient

tracer = trace.get_tracer(__name__)

class VoiceAgent:
    def __init__(self, consumer, session_id="default", job_description=None):
        self.consumer = consumer
        self.session_id = session_id
        self.job_description = job_description or "Software Engineer at a high-growth startup."
        self.is_interrupted = False
        self.current_llm_task = None
        self.is_ai_speaking = False
        self.last_backchannel_time = time.time()
        self.encoding = "linear16"
        
        self.dg_key = os.getenv("DEEPGRAM_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        
        self.dg_client = AsyncDeepgramClient(api_key=self.dg_key)
        self.groq_client = AsyncGroq(api_key=self.groq_key)
        
        self.dg_context = None
        self.dg_connection = None
        self.dg_listener_task = None
        
        self.chat_history = [
            {
                "role": "system", 
                "content": (
                    f"Role: You are 'Vox', a senior HR recruiter. JD: {self.job_description} "
                    "Goals: Capture Summary, Intent, and Timeline. "
                    "Style: Empathetic, human-like. Mirror language (English/Hindi/Hinglish). "
                    "Rule: Use brief backchannels like 'Mm-hmm' during candidate's long turns. "
                    "Guardrails: No salary talk, no legal promises. Redirect to Human HR."
                )
            }
        ]

    async def start_pipeline(self, encoding="linear16"):
        try:
            self.encoding = encoding
            print(f"[Vox] Initializing (Session: {self.session_id}, Encoding: {self.encoding})")
            
            self.dg_context = self.dg_client.listen.v1.connect(
                model="nova-2", smart_format=True, language="en-IN",
                encoding=self.encoding,
                sample_rate=8000 if self.encoding == "mulaw" else 16000,
                interim_results=True, vad_events=True, endpointing=300,
            )
            self.dg_connection = await self.dg_context.__aenter__()

            async def on_message(result, **kwargs):
                try:
                    transcript = ""
                    is_final = False
                    if hasattr(result, "channel"):
                        transcript = result.channel.alternatives[0].transcript
                        is_final = result.is_final
                    
                    if transcript and not is_final and not self.is_ai_speaking:
                        await self.handle_backchannel(transcript)

                    if transcript.strip() and self.is_ai_speaking:
                        if len(transcript) > 2 or is_final:
                            await self.handle_interrupt()

                    if transcript and is_final:
                        await self.consumer.send_transcript("user", transcript)
                        await self.trigger_llm_response(transcript)
                except Exception: pass

            self.dg_connection.on("message", on_message)
            self.dg_listener_task = asyncio.create_task(self.dg_connection.start_listening())
            
        except Exception as e:
            print(f"[Vox-CRITICAL] Engine Startup Failed: {str(e)}")
            raise e

    async def initial_greeting(self):
        greeting = "Hi, I'm Vox from the recruitment team. Is now a good time for a quick chat?"
        await self.consumer.send_transcript("vox", greeting)
        await self.send_to_tts(greeting)
        self.chat_history.append({"role": "assistant", "content": greeting})

    async def handle_backchannel(self, interim_text: str):
        now = time.time()
        if now - self.last_backchannel_time > 4.0:
            choice = random.choice(["I see", "Right", "Mm-hmm", "Okay"])
            await self.send_to_tts(choice)
            self.last_backchannel_time = now

    async def handle_interrupt(self):
        if self.current_llm_task and not self.current_llm_task.done():
            self.current_llm_task.cancel()
        self.is_ai_speaking = False
        await self.consumer.send_interrupt()

    async def trigger_llm_response(self, user_text: str):
        self.is_interrupted = False
        self.is_ai_speaking = True
        self.chat_history.append({"role": "user", "content": user_text})
        if self.current_llm_task and not self.current_llm_task.done():
            self.current_llm_task.cancel()
        self.current_llm_task = asyncio.create_task(self.run_llm_loop())

    async def run_llm_loop(self):
        try:
            response = await self.groq_client.chat.completions.create(
                messages=self.chat_history,
                model="llama-3.3-70b-versatile",
                stream=True
            )

            ai_full_text = ""
            sentence_buffer = ""
            async for chunk in response:
                if self.is_interrupted: break
                content = chunk.choices[0].delta.content or ""
                ai_full_text += content
                sentence_buffer += content
                if any(punct in content for punct in [".", "!", "?", ",", "\n"]):
                    if sentence_buffer.strip():
                        await self.send_to_tts(sentence_buffer.strip())
                        sentence_buffer = ""

            if sentence_buffer.strip() and not self.is_interrupted:
                await self.send_to_tts(sentence_buffer.strip())
            
            if ai_full_text and not self.is_interrupted:
                await self.consumer.send_transcript("vox", ai_full_text)
                self.chat_history.append({"role": "assistant", "content": ai_full_text})

        except asyncio.CancelledError: pass
        except Exception as e: print(f"[LLM Error] {e}")
        finally: self.is_ai_speaking = False

    async def send_to_tts(self, text: str):
        if self.is_interrupted or not text: return
        
        # PERFECTION: Dynamic TTS Encoding for Telephony vs Web
        params = {
            "model": "aura-orpheus-en",
            "encoding": "mulaw" if self.encoding == "mulaw" else "linear16",
            "sample_rate": 8000 if self.encoding == "mulaw" else 16000
        }
        
        url = f"https://api.deepgram.com/v1/speak?model={params['model']}&encoding={params['encoding']}&sample_rate={params['sample_rate']}"
        headers = {"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}", "Content-Type": "application/json"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"text": text}, headers=headers) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        await self.consumer.send_audio(audio_data)
        except Exception: pass

    async def finalize_session(self):
        try:
            summary_prompt = "Provide JSON: {summary, intent_score_1_10, availability_timeline, hr_qa_recap}"
            messages = self.chat_history + [{"role": "system", "content": summary_prompt}]
            resp = await self.groq_client.chat.completions.create(messages=messages, model="llama-3.3-70b-versatile", stream=False)
            analysis = resp.choices[0].message.content
            match = re.search(r'"intent_score_1_10":\s*(\d+)', analysis.lower())
            score = match.group(1) if match else "N/A"
            await self.consumer.send_recap(score, analysis)
        except: pass

    async def process_audio_chunk(self, chunk: bytes):
        if self.dg_connection:
            try: await self.dg_connection.send_media(chunk)
            except Exception: pass

    async def stop_pipeline(self):
        await self.finalize_session()
        if self.dg_listener_task: self.dg_listener_task.cancel()
        if self.dg_context: await self.dg_context.__aexit__(None, None, None)
