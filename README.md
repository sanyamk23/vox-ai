# 🎙️ Project Vox: The Human-Centric Voice AI Recruiter

Project Vox is an ultra-low-latency, production-grade Voice AI screening agent designed to revolutionize the recruitment experience for the modern workforce. Built with a focus on empathy, linguistic mirroring, and "Anyhow" interruption handling, Vox conducts human-like screening rounds that prioritize rapport over technical scraping.

---

## 🚀 Key Features

- **Anyhow Interruption Handling**: Real-time full-duplex communication with sub-500ms latency.
- **Linguistic Mirroring**: Seamlessly transitions between English, Hindi, and Hinglish.
- **Active Listening**: Natural backchanneling engine ("Mm-hmm", "I see", "Right") to mimic human empathy.
- **E2E Phone Bridge**: Integrated Twilio Media Streams for direct outbound candidate screening.
- **Dynamic JD Context**: High-fidelity adaptation to any Job Description on-the-fly.
- **Automated Scorecarding**: Generates actionable HR intelligence (Intent, Fit, Availability) after every session.

---

## 🛠️ Tech Stack

- **Brain**: [Groq](https://groq.com/) (Llama-3.3-70b) for lightning-fast inference.
- **Ears**: [Deepgram Nova-2](https://deepgram.com/) for real-time STT with VAD.
- **Voice**: [Deepgram Aura-Orpheus](https://deepgram.com/) for natural human speech synthesis.
- **Backend**: Django ASGI (Daphne) + WebSockets (Channels).
- **Frontend**: React + TailwindCSS (Glassmorphic Command Center).
- **Infrastructure**: Docker Compose + Redis (Channel Layers).

---

## 📦 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Twilio Account (for phone features)
- Ngrok (for local phone testing)

### 2. Environment Setup
Create a `.env` file in the root directory:

```env
DEEPGRAM_API_KEY=your_key
GROQ_API_KEY=your_key
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_twilio_number
PUBLIC_URL=your_ngrok_url
```

### 3. Launch
```bash
docker-compose up --build
```

---

## 📞 Testing the Phone Bridge

1. Start Ngrok: `ngrok http 8000`
2. Update `PUBLIC_URL` in `.env` with the ngrok link.
3. Verify the candidate's phone number in your Twilio Console.
4. Use the **Command Center** UI to trigger an outbound call.
5. **Note**: If using a Twilio Trial account, press any key on your phone after answering to bridge the AI.

---

## 🧪 Testing & Quality Assurance

Project Vox uses a multi-layered testing strategy (Unit, Component, E2E) to ensure conversational stability.

### Running Tests Locally
Ensure the Docker containers are running, then execute:
```bash
./scripts/run_tests.sh
```

### Pre-commit Hooks
We use `pre-commit` to ensure all tests pass and code is clean before every commit.

1. Install pre-commit:
   ```bash
   pip install pre-commit
   ```
2. Install the hooks:
   ```bash
   pre-commit install
   ```
3. (Optional) Run against all files:
   ```bash
   pre-commit run --all-files
   ```

The pre-commit pipeline includes:
- **Linting**: Trailing whitespace, EOF fixing, YAML validation.
- **Logic Verification**: Automatic execution of the full 18-test suite in the backend container.

---

## 🏗️ Architecture Overview

Project Vox operates on a **Single-Loop Streaming Pipeline**:
1. **Candidate Audio** is streamed via WebSocket (mulaw/linear16).
2. **Deepgram** processes VAD and sends incremental transcripts.
3. **Groq** streams sentence-level responses to maintain conversational tempo.
4. **Deepgram TTS** generates audio chunks which are piped back to the device in real-time.

---

## ⚖️ Guardrails

Vox is instructed to avoid:
- Salary negotiations.
- Legal promises or contract commitments.
- Automated technical scraping (prioritizing conversational rapport).

---

Developed with ❤️ for the future of recruiting.
