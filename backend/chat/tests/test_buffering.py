import pytest
import audioop
import base64

def process_audio_buffer(buffer, target_size=800):
    """Simulated version of the buffering logic in GeminiLiveBridge."""
    chunks_to_send = []
    while len(buffer) >= target_size:
        to_process = buffer[:target_size]
        buffer = buffer[target_size:]

        # Simulate resampling (mulaw 8k -> pcm 16k)
        # In reality this is audioop.ulaw2lin(to_process, 2) then ratecv
        chunks_to_send.append(to_process)
    return chunks_to_send, buffer

def test_buffering_logic():
    # Twilio chunk is 160 bytes (20ms)
    # Target is 800 bytes (100ms)

    buffer = b""
    twilio_chunk = b"x" * 160

    # 1st chunk
    chunks, buffer = process_audio_buffer(buffer + twilio_chunk)
    assert len(chunks) == 0
    assert len(buffer) == 160

    # Add 3 more chunks (total 4)
    for _ in range(3):
        chunks, buffer = process_audio_buffer(buffer + twilio_chunk)
    assert len(chunks) == 0
    assert len(buffer) == 640

    # 5th chunk (reaches 800)
    chunks, buffer = process_audio_buffer(buffer + twilio_chunk)
    assert len(chunks) == 1
    assert len(chunks[0]) == 800
    assert len(buffer) == 0

def test_buffering_overflow():
    buffer = b""
    large_chunk = b"x" * 1000 # More than 800

    chunks, buffer = process_audio_buffer(buffer + large_chunk)
    assert len(chunks) == 1
    assert len(chunks[0]) == 800
    assert len(buffer) == 200

def test_buffering_extreme_cases():
    # Exactly target size
    chunks, buffer = process_audio_buffer(b"x" * 800)
    assert len(chunks) == 1
    assert len(buffer) == 0

    # Multiple target sizes
    chunks, buffer = process_audio_buffer(b"x" * 2000)
    assert len(chunks) == 2
    assert len(chunks[0]) == 800
    assert len(chunks[1]) == 800
    assert len(buffer) == 400

    # Very small chunks
    buffer = b""
    for _ in range(800):
        chunks, buffer = process_audio_buffer(buffer + b"x")
    assert len(chunks) == 1
    assert len(buffer) == 0
