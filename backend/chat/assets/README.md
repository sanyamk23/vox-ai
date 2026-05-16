# Voice Agent Assets

This directory contains audio assets used to enhance the realism of the voice agent.

## Required Files
- `background_noise.wav`: Continuous ambient sound (e.g., office noise, room tone).
- `keyboard_click.wav`: A single keyboard click sound.
- `breath.wav`: A natural human breath sound.

## Formatting
- Use **WAV** format (8000Hz for Twilio, 22050Hz+ for Web).
- The code will automatically resample these to match the agent's output, but keeping them as WAV avoids the need for `ffmpeg`.

## How it works
The `VoiceAgent` class in `agent.py` will:
1. Load these files on startup.
2. Overlay `background_noise` at -25dB.
3. Randomly insert `keyboard_click` sounds during the speech.
4. Prepend a `breath` sound to some sentences.
