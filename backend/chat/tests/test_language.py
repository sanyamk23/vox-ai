import pytest
import re
from chat.agent import _HINGLISH_KEYWORDS, _DEVANAGARI_RE

def detect_hindi(text):
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    words = set(clean_text.split())
    return bool(_DEVANAGARI_RE.search(text) or any(w in _HINGLISH_KEYWORDS for w in words))

def test_pure_english():
    assert detect_hindi("Hello, how are you doing today?") is False
    assert detect_hindi("I have worked on React and Django for 2 years.") is False

def test_pure_hindi_devanagari():
    assert detect_hindi("नमस्ते, आप कैसे हैं?") is True
    assert detect_hindi("मुझे समझ नहीं आ रहा।") is True

def test_hinglish_romanized():
    assert detect_hindi("Haan, actually mujhe samajh nahi aa raha.") is True
    assert detect_hindi("Haan, bilkul theek hai.") is True
    assert detect_hindi("Toh basically hum production bugs fix karte hain.") is True

def test_mixed_hinglish():
    assert detect_hindi("I have experience in Django, par React thoda kam aata hai.") is True
    assert detect_hindi("Notice period mera 15 days ka hai.") is True

def test_language_edge_cases():
    # Only numbers and acronyms should be English
    assert detect_hindi("12 LPA, 15 days notice.") is False
    assert detect_hindi("CTC, HR, JD.") is False

    # Very short strings
    assert detect_hindi("Haan.") is True
    assert detect_hindi("Yes.") is False

    # Punctuation and cases
    assert detect_hindi("!!! ACHHA !!!") is True
    assert detect_hindi("...okay...") is False

    # Empty or whitespace
    assert detect_hindi("") is False
    assert detect_hindi("   ") is False

    # Mixed script (Devanagari anywhere)
    assert detect_hindi("Working on Django and React (नमस्ते)") is True
