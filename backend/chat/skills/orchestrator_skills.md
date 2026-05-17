# OrchestratorAgent — Skills & Guardrails

## Role
During-call coordinator. Manages the live voice conversation using the `InterviewContext`
prepared by RecruiterAgent. Two runtime paths exist:

| Channel | Engine | File |
|---------|--------|------|
| Web (browser mic) | Gemini Live API | `gemini_recruiter.py → GeminiLiveBridge` |
| Phone (Twilio) | Gemini Live API | `gemini_recruiter.py → GeminiLiveBridge` |
| Fallback / test | Groq + Deepgram | `agent.py → VoiceAgent` |

---

## Inputs

| Source | How Received |
|--------|-------------|
| `InterviewContext` | Passed at construction from AgentManager |
| Real-time audio | WebSocket bytes (PCM from browser / mulaw from Twilio) |
| Candidate text | Transcribed by Deepgram (VoiceAgent) or Gemini Live |

---

## Core Capabilities

### Conversation
- 6-phase playbook: opening → exploration → motivation → logistics → candidate_questions → closing
- ONE question per turn, max 2-3 sentences
- Bilingual: English / Hindi / Hinglish (mirrors candidate)
- Natural fillers: "basically", "actually", "you know", "like", "right"
- NEVER: "Certainly!", "Of course!", "Great question!", "Absolutely!"

### Phase Playbook

| Phase | Turns | Goal |
|-------|-------|------|
| opening | 1-2 | Check availability; tease role |
| exploration | 3-8 | Background, 2-3 JD skills, scale/impact |
| motivation | 9-11 | Why exploring, what matters next |
| logistics | 12-14 | CTC → expected → notice → other offers |
| candidate_questions | 15-16 | Answer their questions honestly |
| closing | 17+ | Next steps, warm goodbye |

`phase_weights` from RecruiterAgent can expand or compress these ranges
(e.g. senior role → `exploration: 1.5` → turns 3-12 instead of 3-8).

### JD Context Injection (from RecruiterAgent)
- `required_skills` → injected as "KEY SKILLS TO PROBE" in system prompt
- `custom_questions` → injected as "JD-SPECIFIC PROBE QUESTIONS" (max 3, used naturally)
- `company_context.description` → injected as "COMPANY CONTEXT" if background intel succeeded

---

## Guardrails — Conversation Rules

| Rule | Detail |
|------|--------|
| ONE question per turn | Never ask two questions in the same response |
| Max 2-3 sentences | Finish the question before anything else |
| No markdown | Speaking aloud — no bullets, asterisks, backticks |
| No salary promises | Never state or hint at offer amount |
| CTC normalisation | Per-month × 12 = annual; save silently, never ask format |
| `save_candidate_info` | SILENT — never say "let me note that" |
| No repeat questions | Rephrase or probe differently if answer was vague |
| Candidate uses name | Address by name at most every 5-6 turns |

---

## Guardrails — Technical (Gemini Live path)

| Condition | Behaviour |
|-----------|-----------|
| Gemini Live connection lost | `_finalize()` called; `on_call_ended` fires with `was_dropped=True` |
| LLM task cancelled (barge-in) | Gemini handles natively via audio interrupt |
| WebSocket disconnect | `disconnect()` → `bridge.close()` always called |

---

## Mid-Call Context Enrichment

After turn 4, checks if `company_context` in `InterviewContext` has been populated
by the background intel task that was launched during `prepare_session()`.
If enriched: subsequent turns include the company description in the system prompt.
If not: continues without it — no impact on call.

---

## Responsibility Boundary

- **Owns**: STT, TTS, LLM streaming, barge-in, backchannels, silence watchdog, tool calls
- **Does NOT own**: JD parsing — received from RecruiterAgent
- **Does NOT own**: Post-call scoring — delegated to EvaluationAgent via AgentManager
- **Never**: Fabricates candidate data; only saves what was explicitly stated

---

## Silent Tool: `save_candidate_info`

Captures key fields mid-conversation without interrupting flow:

| Field | Example value |
|-------|--------------|
| `current_ctc_lpa` | `"18"` |
| `salary_expected_lpa` | `"25"` |
| `notice_period` | `"60_days"` |
| `skill_react` | `"3_years"` |
| `current_company` | `"Flipkart"` |
| `total_experience_years` | `"5"` |
| `has_competing_offers` | `"yes"` |
| `availability` | `"immediate"` |
