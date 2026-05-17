# RecruiterAgent — Skills & Guardrails

## Role
Pre-call intelligence. Runs **before** the call starts (~1s). Produces an `InterviewContext`
that OrchestratorAgent uses to build a smarter system prompt and ask better questions.

---

## Inputs

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `jd` | string | Yes | Raw job description text |
| `candidate_name` | string | No | Used for logging only |

---

## Outputs — `InterviewContext`

| Field | Type | Description |
|-------|------|-------------|
| `job_title` | str | Extracted or inferred from JD |
| `company_name` | str | Company name (empty if not found) |
| `required_skills` | list[str] | Max 10 must-have skills |
| `nice_to_have_skills` | list[str] | Max 5 bonus skills |
| `experience_level` | str | junior / mid / senior / lead / principal |
| `domain` | str | fintech, edtech, SaaS, infra, general … |
| `custom_questions` | list[str] | Max 3 JD-specific probe questions |
| `phase_weights` | dict | Float multipliers per phase (0.5–2.0) |
| `company_context` | dict | Async-enriched later (Wikipedia summary) |
| `salary_range` | str|None | If recruiter provided it |
| `raw_jd` | str | Original JD text (truncated to 500 chars for storage) |
| `recruiter_status` | str | `completed` / `fallback_used` |

---

## Tools

| Tool | Purpose | Timeout |
|------|---------|---------|
| Groq LLM (llama-3.3-70b) | JD parsing + question generation | 8s (1 retry) |
| aiohttp → Wikipedia REST API | Background company intel fetch | 8s (no retry) |

---

## Guardrails

| Condition | Behaviour |
|-----------|-----------|
| JD text < 20 chars | Skip LLM call — immediate fallback |
| LLM returns invalid JSON | Retry once, then fallback |
| LLM timeout > 8s | Retry once, then fallback |
| All retries exhausted | Return `InterviewContext(raw_jd=jd, recruiter_status="fallback_used")` |
| Company intel fetch fails | Silent discard — call starts without it |
| `company_name` is empty | Skip background intel task entirely |

**Fallback guarantee**: `run_with_guardrails()` always returns an `InterviewContext`.
The fallback context preserves the raw JD so `build_vox_system_prompt()` behaves
exactly as it did before the agent layer existed — zero regression.

---

## Phase Weight Rules

| Condition | Adjustment |
|-----------|-----------|
| `experience_level` is senior/lead/principal | `exploration: 1.5` |
| JD mentions "founding engineer" or "startup" | `motivation: 1.5` |
| JD mentions relocation or contract | `logistics: 1.5` |
| Anything else | All weights default to `1.0` |

---

## Responsibility Boundary

- **Owns**: JD parsing, question generation, background company intel
- **Does NOT own**: Live conversation, STT, TTS, LLM turn-by-turn reasoning
- **Does NOT own**: Post-call scoring — that belongs to EvaluationAgent
- **Never**: Promises salary, role, timeline, or rejection to the candidate

---

## Health Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Not yet run |
| `running` | In progress |
| `completed` | Success — full InterviewContext available |
| `fallback_used` | Failed/timed out — minimal context returned |
| `timed_out` | Exceeded 8s — fallback triggered |
| `failed` | Unhandled exception — fallback triggered |
