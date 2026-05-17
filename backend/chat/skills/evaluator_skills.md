# EvaluationAgent — Skills & Guardrails

## Role
Post-call scoring. Runs **after** the call ends (no latency pressure). Produces a
structured `EvalReport` with four dimension scores, confidence values, and a decision.

---

## Inputs

| Field | Type | Notes |
|-------|------|-------|
| `transcript` | list[dict] | Full role/content chat history (system messages excluded) |
| `live_notes` | dict | Fields captured silently via `save_candidate_info` during call |
| `context` | InterviewContext | JD intelligence for scoring against requirements |

---

## Outputs — `EvalReport`

### Top-level decision
| Field | Type | Description |
|-------|------|-------------|
| `intent_score` | int 1-10 | 10=extremely excited, 1=clearly not interested |
| `call_outcome` | str | INTERESTED / BUSY / NOT_INTERESTED / CALLBACK_REQUESTED / CONFUSED |

### Dimension scores (each has score 1-10, confidence 0-1, evidence quotes)
| Dimension | What it measures |
|-----------|-----------------|
| `technical_fit` | Skills match vs JD `required_skills` |
| `communication` | Clarity, articulation, language confidence |
| `motivation_fit` | Genuine interest, energy, alignment with role |
| `logistics_fit` | Salary fit vs range, notice period, availability |

### Summary fields
| Field | Type | Description |
|-------|------|-------------|
| `overall_confidence` | float 0-1 | Aggregate confidence across all dimensions |
| `summary_bullets` | list[str] | 3-5 specific quotes from the call |
| `skills_verified` | list[str] | Skills candidate explicitly confirmed |
| `salary_expectation_lpa` | float|None | Null if not discussed |
| `current_ctc_lpa` | float|None | Null if not discussed |
| `notice_period_days` | int|None | Null if not discussed |
| `joining_timeline` | str|None | Candidate's own words |
| `other_offers` | bool|None | True if interviewing elsewhere |
| `hr_flags` | list[str] | Red flags (empty if none) |
| `vibe_check` | str | One honest sentence about energy and fit |
| `recommended_next_step` | str | Specific action for the hiring team |
| `reasoning` | str | 2-3 sentences explaining score + outcome |
| `evaluator_status` | str | `completed` / `fallback_used` |

---

## Tools

| Tool | Purpose | Timeout |
|------|---------|---------|
| Groq LLM (llama-3.3-70b) | Multi-dimensional evaluation | 20s (2 retries) |

---

## Guardrails

| Condition | Behaviour |
|-----------|-----------|
| LLM timeout > 20s | Retry up to 2 times, then fallback |
| LLM returns invalid JSON | Retry up to 2 times, then fallback |
| Short call (≤ 2 turns) | Low-confidence fallback; all dimension confidences ≤ 0.2 |
| No JD context available | Score only communication and logistics dimensions |
| All retries exhausted | Fallback EvalReport built from `live_notes` |

**Fallback guarantee**: `run_with_guardrails()` always returns an `EvalReport`.
The fallback extracts skills, salary, and notice period from `live_notes`
(captured silently during the call via `save_candidate_info`) — no data is lost.

---

## Scoring Rules

1. **Null = not discussed** — never infer or fabricate
2. `overall_confidence < 0.4` → add flag: `"Insufficient data — manual review required"`
3. `technical_fit.confidence` must be LOW (`< 0.4`) for calls ≤ 5 turns
4. `hr_flags` must include:
   - Salary expectation above JD range (if range is known)
   - Notice period > 90 days
   - Strong competing offers with tight deadline
   - Evasive or contradictory answers

---

## Outcome Decision Matrix

| Condition | Outcome |
|-----------|---------|
| `technical_fit.score < 4` | NOT_INTERESTED |
| Salary mismatch or notice > 90d | CALLBACK_REQUESTED |
| `intent_score ≥ 7` AND `technical_fit.score ≥ 6` | INTERESTED |
| Candidate was unavailable / busy | BUSY |
| Insufficient signals | CONFUSED |

---

## Fallback EvalReport Fields

When all LLM retries fail, the fallback is built from `live_notes`:

| Source | Target |
|--------|--------|
| `live_notes["skill_*"]` | `skills_verified` |
| `live_notes["salary_expected_lpa"]` | `salary_expectation_lpa` |
| `live_notes["current_ctc_lpa"]` | `current_ctc_lpa` |
| `live_notes["notice_period"]` | `notice_period_days` (parsed) |
| Hardcoded | `hr_flags: ["Auto-evaluation failed — manual review required"]` |
| Hardcoded | `overall_confidence: 0.0` |

---

## Responsibility Boundary

- **Owns**: Post-call scoring, dimension analysis, outcome decision, EvalReport
- **Does NOT own**: Live conversation — that's OrchestratorAgent
- **Does NOT own**: JD parsing — that's RecruiterAgent
- **Never**: Promises or communicates results to the candidate
- **Never**: Makes hiring decisions — provides data for the hiring team to decide
