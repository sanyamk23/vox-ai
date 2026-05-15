"""
LLM Service — Hardened, production-grade LLM orchestration.

Features:
- Retry with exponential backoff
- Streaming sentence-level output
- Structured JSON output parsing (no regex)
- Context window management with automatic summarization
- MCP tool-calling integration
- Proper error propagation (no silent swallowing)

Open/Closed: Swap the LLM provider by subclassing BaseLLMService.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Any

from groq import AsyncGroq

logger = logging.getLogger("vox.llm")

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_HISTORY_MESSAGES = 40          # Trigger summarization after this many messages
SUMMARY_KEEP_RECENT = 10          # Keep the N most recent messages after summarization
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.5            # seconds — doubles each retry
SENTENCE_DELIMITERS = {".", "!", "?", "\n"}


# ─── Abstract Base ───────────────────────────────────────────────────────────

class BaseLLMService(ABC):
    """
    Abstract LLM service. Extend this to swap providers (Groq, OpenAI, local, etc.)
    without modifying the VoiceAgent.
    """

    @abstractmethod
    async def stream_response(
        self,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> AsyncIterator[str]:
        """Yield response text token-by-token."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: List[dict],
        response_format: Optional[dict] = None,
    ) -> str:
        """Return a single complete response (non-streaming)."""
        ...


# ─── Groq Implementation ─────────────────────────────────────────────────────

class GroqLLMService(BaseLLMService):
    """
    Production LLM service backed by Groq Cloud.
    """

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ):
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = AsyncGroq(api_key=api_key or os.getenv("GROQ_API_KEY"))

    # ── Streaming ─────────────────────────────────────────────────────────

    async def stream_response(
        self,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM with retry logic.
        Yields individual content strings (not full sentences — the caller buffers).
        """
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = dict(
                    messages=messages,
                    model=self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    stream=True,
                )
                if tools:
                    kwargs["tools"] = tools

                response = await self._client.chat.completions.create(**kwargs)

                async for chunk in response:
                    delta = chunk.choices[0].delta
                    content = delta.content or ""
                    if content:
                        yield content

                return  # Success — exit retry loop

            except asyncio.CancelledError:
                raise  # Always propagate cancellation
            except Exception as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"[LLM] Stream attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        logger.error(f"[LLM] All {MAX_RETRIES} stream attempts failed: {last_error}")
        raise last_error

    # ── Non-streaming (for scorecards, summarization) ─────────────────────

    async def complete(
        self,
        messages: List[dict],
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Single-shot completion with retry. Used for structured outputs like
        session scorecards and conversation summarization.
        """
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = dict(
                    messages=messages,
                    model=self._model,
                    temperature=0.3,  # Lower temp for structured outputs
                    stream=False,
                )
                if response_format:
                    kwargs["response_format"] = response_format

                resp = await self._client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content

            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"[LLM] Complete attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        logger.error(f"[LLM] All {MAX_RETRIES} complete attempts failed: {last_error}")
        raise last_error


# ─── Sentence Chunker ────────────────────────────────────────────────────────

async def stream_sentences(
    llm: BaseLLMService,
    messages: List[dict],
    tools: Optional[List[dict]] = None,
) -> AsyncIterator[str]:
    """
    High-level helper: streams from the LLM and yields complete sentences.
    Buffers tokens and flushes on sentence-ending punctuation.
    This is the DRY replacement for the inline sentence-splitting in the old agent.
    """
    buffer = ""
    async for token in llm.stream_response(messages, tools):
        buffer += token
        # Flush on sentence boundaries
        if any(delim in token for delim in SENTENCE_DELIMITERS):
            sentence = buffer.strip()
            if sentence:
                yield sentence
            buffer = ""

    # Flush any remaining text
    remainder = buffer.strip()
    if remainder:
        yield remainder


# ─── Context Management ──────────────────────────────────────────────────────

SUMMARIZATION_PROMPT = (
    "You are a conversation summarizer. Condense the conversation above into a brief "
    "paragraph capturing: key candidate details mentioned, questions asked and answers given, "
    "and any notable signals (positive or negative). Be factual and concise."
)


async def maybe_summarize_history(
    llm: BaseLLMService,
    chat_history: List[dict],
) -> List[dict]:
    """
    If chat_history exceeds MAX_HISTORY_MESSAGES, summarize the older messages
    into a single 'system' message and keep only the most recent ones.
    This prevents context window overflow on long screening calls.

    Returns a new list — does not mutate the input.
    """
    if len(chat_history) <= MAX_HISTORY_MESSAGES:
        return chat_history

    logger.info(
        f"[LLM] Context window management: summarizing {len(chat_history)} messages"
    )

    # Preserve the original system prompt (always index 0)
    system_prompt = chat_history[0]
    older_messages = chat_history[1:-SUMMARY_KEEP_RECENT]
    recent_messages = chat_history[-SUMMARY_KEEP_RECENT:]

    # Ask the LLM to summarize the older portion
    summary_request = older_messages + [
        {"role": "system", "content": SUMMARIZATION_PROMPT}
    ]

    try:
        summary_text = await llm.complete(summary_request)
        condensed_history = [
            system_prompt,
            {
                "role": "system",
                "content": f"[Conversation summary so far]: {summary_text}",
            },
            *recent_messages,
        ]
        logger.info(
            f"[LLM] Summarized {len(older_messages)} messages → "
            f"{len(condensed_history)} total"
        )
        return condensed_history

    except Exception as e:
        logger.warning(f"[LLM] Summarization failed, keeping full history: {e}")
        return chat_history


# ─── Structured Scorecard Parsing ─────────────────────────────────────────────

SCORECARD_PROMPT = """\
Analyze the screening conversation above and produce a JSON assessment.
Respond ONLY with valid JSON — no markdown, no commentary.

Required schema:
{
  "summary": "2-3 sentence candidate overview",
  "intent_score": 8,
  "intent_reasoning": "Why this score",
  "availability_timeline": "e.g. 30 days notice",
  "strengths": ["strength1", "strength2"],
  "concerns": ["concern1"],
  "recommendation": "proceed | hold | reject",
  "hr_notes": "Any additional notes for the human HR team"
}
"""


async def generate_scorecard(
    llm: BaseLLMService,
    chat_history: List[dict],
) -> Dict[str, Any]:
    """
    Generate a structured scorecard from the conversation.
    Uses proper JSON parsing instead of regex extraction.
    """
    messages = chat_history + [
        {"role": "system", "content": SCORECARD_PROMPT}
    ]

    try:
        raw = await llm.complete(
            messages,
            response_format={"type": "json_object"},
        )
        scorecard = json.loads(raw)
        logger.info(f"[LLM] Scorecard generated: intent={scorecard.get('intent_score')}")
        return scorecard

    except json.JSONDecodeError:
        logger.warning("[LLM] Scorecard JSON parse failed, returning raw text")
        return {
            "summary": raw if 'raw' in dir() else "Parse error",
            "intent_score": "N/A",
            "recommendation": "review_manually",
            "raw_response": raw if 'raw' in dir() else None,
        }
    except Exception as e:
        logger.error(f"[LLM] Scorecard generation failed: {e}")
        return {
            "summary": "Scorecard generation failed",
            "intent_score": "N/A",
            "recommendation": "review_manually",
            "error": str(e),
        }
