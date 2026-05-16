import pytest
from unittest.mock import MagicMock
from chat.agent import VoiceAgent, _phase_for, _BARGE_IN_FILLERS

@pytest.fixture
def mock_agent():
    # We mock the constructor dependencies
    mock_consumer = MagicMock()
    agent = VoiceAgent(
        consumer=mock_consumer,
        candidate_name="Test Candidate",
        job_description="Test JD",
        session_id="test_session"
    )
    # Mock external connections
    agent.dg_connection = MagicMock()
    return agent

def test_phase_logic():
    # Initial phase
    assert _phase_for(0) == "opening"
    assert _phase_for(5) == "exploration"
    assert _phase_for(10) == "motivation"
    assert _phase_for(13) == "logistics"
    assert _phase_for(16) == "candidate_questions"
    assert _phase_for(20) == "closing"

def test_barge_in_logic():
    # Logic from on_message
    def is_filler(transcript):
        words = transcript.strip().lower().split()
        return (
            len(words) <= 2
            and all(w.strip(".,!?") in _BARGE_IN_FILLERS for w in words)
        )

    assert is_filler("hmm") is True
    assert is_filler("yeah") is True
    assert is_filler("actually, i have a question") is False
    assert is_filler("Wait, what?") is False

def test_context_note_generation(mock_agent):
    mock_agent.turn_count = 13
    note = mock_agent._build_context_note()
    assert "LOGISTICS phase" in note
    assert "salary" in note.lower()
