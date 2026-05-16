import pytest
from unittest.mock import MagicMock, AsyncMock
from chat.agent import VoiceAgent, _phase_for

def simulate_call_flow(persona_name, turns):
    """
    Visualizes how the AI is programmed to handle specific human behaviors.
    """
    print(f"\n--- SIMULATING CALL: {persona_name} ---")

    # We use the logic we've built to predict the AI's response pattern
    for i, (user_input, behavior) in enumerate(turns):
        phase = _phase_for(i)

        # Determine AI Language Logic (Simplified representation of our prompt rules)
        ai_lang = "English"
        if any(word in user_input.lower() for word in ["haan", "achha", "samajh"]):
            ai_lang = "Hindi/Hinglish (Mirroring)"

        # Empowerment Logic
        is_hesitant = "..." in user_input or "um" in user_input.lower()
        if is_hesitant and ai_lang == "English":
            behavior += " [AI EMPOWERMENT: Staying in English, using simpler words]"

        print(f"Turn {i} ({phase}):")
        print(f"  User: \"{user_input}\"")
        print(f"  Logic: {behavior}")
        print(f"  AI Lang: {ai_lang}")
        print("-" * 20)

def test_visualize_hesitant_candidate():
    turns = [
        ("Hello, yes I am ready.", "Normal opening"),
        ("I... um... work on React but... it's difficult to explain in English...", "Hesitation detected"),
        ("I try my best to speak in English because it's professional.", "Persistence in English"),
    ]
    simulate_call_flow("The Hesitant Professional", turns)

def test_visualize_language_pivot():
    turns = [
        ("Hi, I am Sanyam.", "English start"),
        ("Haan, actually main Django pe 2 saal se kaam kar raha hoon.", "Switch to Hindi (Mirroring triggered)"),
        ("But regarding the architecture, I prefer explaining in English: I use a microservices approach.", "Switch back to English (Strict Reciprocity)"),
    ]
    simulate_call_flow("The Multi-lingual Pivot", turns)
