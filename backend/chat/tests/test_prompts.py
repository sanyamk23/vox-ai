import pytest
from chat.agent import build_vox_system_prompt
from chat.gemini_recruiter import build_sarah_system_prompt

def test_vox_system_prompt_structure():
    prompt = build_vox_system_prompt("Sanyam", "Senior React Developer")
    assert "# IDENTITY & PERSONA" in prompt
    assert "# SCREENING FRAMEWORK (6 PHASES)" in prompt
    assert "# LINGUISTIC MIRRORING & EMPOWERMENT" in prompt
    assert "Sanyam" in prompt
    assert "Senior React Developer" in prompt

def test_sarah_system_prompt_structure():
    prompt = build_sarah_system_prompt("Senior Django Lead", "Noe")
    assert "# IDENTITY & PERSONA" in prompt
    assert "# LINGUISTIC MIRRORING & EMPOWERMENT" in prompt
    assert "Noe" in prompt
    assert "Senior Django Lead" in prompt

def test_vox_prompt_defaults():
    prompt = build_vox_system_prompt()
    assert "there" in prompt
    assert "Software Engineer" in prompt
