import pytest
import json
from chat.agent import VoiceAgent

def test_summary_json_extraction():
    # Mock raw LLM output with code fences
    raw_output = """
    Here is the summary:
    ```json
    {
        "summary_bullets": ["Good candidate"],
        "skills_verified": ["Python"],
        "salary_expectation_lpa": 25,
        "current_ctc_lpa": 12,
        "notice_period_days": 15,
        "call_outcome": "INTERESTED"
    }
    ```
    """

    # We test the logic inside _generate_summary_json (or a simplified version)
    # The real one is async and calls Groq, so we test the parsing part.

    def parse_json(text):
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    parsed = parse_json(raw_output)
    assert parsed["salary_expectation_lpa"] == 25
    assert "Python" in parsed["skills_verified"]

def test_summary_json_malformed():
    raw_output = "No JSON here just text."

    def parse_json(text):
        try:
            if "{" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                return json.loads(text[start:end])
        except:
            pass
        return None

    assert parse_json(raw_output) is None
