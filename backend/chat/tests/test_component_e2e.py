import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from chat.gemini_recruiter import GeminiLiveBridge
from chat.models import CallSession
from django.utils import timezone

@pytest.mark.asyncio
async def test_gemini_bridge_e2e_flow(db):
    # Mock the Gemini Live Session response
    mock_turn = MagicMock()
    mock_turn.text = json.dumps({
        "summary_bullets": ["Strong background"],
        "skills_verified": ["React"],
        "salary_expectation_lpa": 30,
        "current_ctc_lpa": 15,
        "notice_period_days": 30,
        "intent_score": 9,
        "call_outcome": "INTERESTED"
    })

    # Setup the bridge
    mock_consumer = AsyncMock()
    bridge = GeminiLiveBridge(
        mode="web",
        system_prompt="Test Prompt",
        candidate_name="Sanyam",
        candidate_phone="+919876543210",
        job_description="Senior Dev",
        call_channel="web",
        on_transcript=AsyncMock(),
        finalize_consumer=mock_consumer
    )

    # 1. Test Audio Feeding (Adds to queue)
    bridge.feed_pcm(b"x" * 1600)
    assert bridge._inbound_pcm.qsize() == 1

    # 2. Test Transcript Aggregation
    await bridge._transcript_agg.push("vox", "Hello", finished=True)
    assert "AI: Hello" in bridge.transcript

    # 3. Test Finalization and DB Persistence
    with patch('google.genai.Client') as mock_genai_client:
        # Mock the summary generation call in agent.py's finalize_gemini_session
        mock_genai_client.return_value.models.generate_content = MagicMock(return_value=mock_turn)

        await bridge._finalize()

        # Verify DB entry
        session = await CallSession.objects.aget(candidate_name="Sanyam")
        assert session.job_description == "Senior Dev"
        assert session.intent_score == 9
        assert session.call_outcome == "INTERESTED"

@pytest.mark.asyncio
async def test_transcript_aggregator_flow():
    # Test the TurnTranscriptAggregator separately as it's a key component
    from chat.gemini_recruiter import TurnTranscriptAggregator

    flushed_turns = []
    async def on_flush(role, text):
        flushed_turns.append((role, text))

    agg = TurnTranscriptAggregator(on_flush=on_flush)

    # Simulate partial turns
    await agg.push("vox", "Hello ", finished=False)
    assert len(flushed_turns) == 0

    # Finish turn
    await agg.push("vox", "world!", finished=True)
    assert len(flushed_turns) == 1
    assert flushed_turns[0] == ("vox", "Hello world!")
