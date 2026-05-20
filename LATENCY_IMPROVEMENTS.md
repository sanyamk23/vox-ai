# Latency & Performance Improvements

This document lists the specific things in the current codebase that add unnecessary weight or latency, ordered by impact.

---

## 1. `sync_to_async` wrappers on every DB/Redis call (High impact)

**Where:** `views.py:529`, `campaign_views.py:416, 422, 442`, `twilio_consumer.py:61`

Every ORM call is wrapped in `sync_to_async()` because Django's ORM is synchronous. Each wrapper dispatches to a thread pool, waits for the thread, and returns — that's an extra context switch on every hot-path operation.

A single `POST /api/call/` hits **5 separate `sync_to_async` calls** before the call is placed:
1. Rate limit check
2. Active call check
3. `_place_call` (which itself calls Twilio + 2 Redis writes + 1 DB write)
4. Session pre-creation

**Fix:** Use async-native DB access (`Django 4.1+ async ORM`, SQLAlchemy async, or Tortoise-ORM). One `await` per operation instead of one thread dispatch.

---

## 2. Gemini Live connection cold-start (~2–4 s per call)

**Where:** `gemini_recruiter.py:569`

```python
async with ai_client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as session:
```

Every call creates a **brand-new Gemini Live WebSocket session** from scratch. That includes:
- TLS handshake to Google
- API key authentication
- Sending the full system prompt (~1 KB of text) as the first message
- Waiting for the model to acknowledge before audio can flow

The candidate hears silence for 2–4 seconds after picking up. The greeting cannot play until this completes.

**Fix (partial):** The pre-caching task (`_precache_interview_context`) already tries to warm the interview context before the call connects, but it doesn't pre-open the Gemini session itself. The cold-start is largely unavoidable at the API level, but buffering early Twilio audio and replaying it once Gemini is ready would mask the gap.

---

## 3. JD context parse blocks the WebSocket on cache miss

**Where:** `twilio_consumer.py:128–142`

If the pre-cache task hasn't finished by the time the candidate picks up, the WebSocket handler falls back to parsing the JD synchronously:

```python
if context is None:
    manager = AgentManager(...)
    context = await manager.prepare_session(jd=jd, ...)
```

`prepare_session` likely calls an LLM or does heavy text processing. This blocks audio flow for the entire duration. The candidate hears dead silence.

**Fix:** Always ensure pre-cache completes before the call is placed (await it before returning from `/api/call/`), or at minimum reduce the pre-cache time so the race is usually won.

---

## 4. Twilio client created fresh on every call

**Where:** `views.py:291`

```python
client = Client(account_sid, auth_token)  # new instance every call
call = client.calls.create(...)
```

`Client()` initialises the Twilio SDK, sets up the HTTP session, and creates internal state on every single outbound call. It's also synchronous, so it blocks a thread for the duration of the Twilio REST round-trip (~300–600 ms).

**Fix:** Create a module-level singleton `_TWILIO_CLIENT` at startup and reuse it. Saves ~50 ms of init overhead per call plus keeps HTTP connections alive across calls.

---

## 5. Pre-created `CallSession` on every initiated call

**Where:** `views.py:327–346`

A `CallSession` DB row is written at the moment the call is placed — before the candidate even picks up. If they don't answer, the row stays and must be updated by the status webhook later. This means:

- 1 DB write on call initiation (whether answered or not)
- 1 DB update on no-answer/busy/failed webhook
- Extra rows for every unanswered call polluting the sessions list

**Fix:** Create the `CallSession` row only when the Twilio "start" event fires (i.e., candidate answered). Use only Redis for the pre-answer state. Cuts ~30% of DB writes for campaigns with poor answer rates.

---

## 6. Campaign loop polls the DB every 5 seconds

**Where:** `campaign_views.py:485–499` (`_wait_for_call_end`)

```python
for _ in range(timeout // 5):   # up to 120 iterations
    await asyncio.sleep(5)
    done = CallSession.objects.filter(call_sid=...).values_list("ended_at").first()
    if done: return
```

For a 10-minute call, this fires **120 DB queries** just to detect that the call ended. Multiply by the number of candidates.

Also, every loop iteration re-fetches the full `Campaign` row (`Campaign.objects.get(id=...)`) to check if it's still running — another query per candidate.

**Fix:** Use Redis pub/sub or a simple asyncio `Event`. When the status webhook or `finalize_gemini_session` stamps `ended_at`, it also publishes to a Redis channel. The campaign loop subscribes and wakes up immediately instead of polling.

---

## 7. Heavy imports inside request handlers (cold-start penalty)

**Where:** `views.py:122–132`, `views.py:253`, `views.py:571`, `campaign_views.py:447`

```python
# Inside a request handler, on every first call:
import pypdf
import docx
from .agent import DEFAULT_VOICE_ID, VOICE_PROFILES
from .retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY
from .models import CallSession
```

Python caches imports after the first load, but on container startup the first request to each endpoint pays the full import cost. `pypdf` and `python-docx` are especially heavy.

**Fix:** Move all imports to module level. The first request sees no extra cost, and the code is cleaner.

---

## 8. `list_sessions` computes aggregates in Python

**Where:** `views.py:731–785`

```python
qs = CallSession.objects.all().order_by("-created_at")
total = qs.count()               # full table COUNT(*)
sessions = qs[offset:offset+limit]

# then in Python:
for session in sessions:
    total_score += session.intent_score
    outcome_counts[outcome] += 1
```

Aggregate stats (average score, outcome breakdown) are computed by pulling records into Python and looping. As the sessions table grows this gets slower. The `qs.count()` also hits the DB separately from the data fetch.

**Fix:** Use `aggregate()` and `values().annotate()` to push all counting and averaging into a single SQL query. Use `only()` to avoid loading large JSON columns (notes, dimension_scores, transcript) when only summary fields are needed.

---

## 9. Audio resampling on every 20 ms packet

**Where:** `gemini_recruiter.py:666–668`, `gemini_recruiter.py:694–699`

```python
pcm_16k, state = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, state)
```

Both inbound (Twilio→Gemini) and outbound (Gemini→Twilio) audio is resampled on every packet. For a 15-minute call that's ~4,500 resampling operations per direction. `audioop` is a C extension so it's fast, but the overhead adds up under load when multiple concurrent calls are running.

**Fix:** Low priority — `audioop` is already near-optimal for this. Batching multiple packets before resampling could reduce call overhead but risks introducing audio latency. Acceptable as-is for small concurrency.

---

## 10. Session state stored in three places simultaneously

**Where:** `views.py:311–344`

The same session data is written to:
1. `Redis vox:{token}` — for WebSocket lookup
2. `Redis vox:call:{call_sid}` — for status webhook lookup
3. `PostgreSQL CallSession.session_data` — for restart resilience

This is intentional redundancy (Redis eviction resilience), but it means every call initiation does **3 writes** where 2 might suffice. The DB copy of `session_data` is a JSON blob that duplicates what the model columns already store.

**Fix:** Drop `CallSession.session_data` (the JSON blob fallback). If Redis evicts, re-fetch the structured DB columns directly. Reduces write amplification and DB storage.

---

## Quick wins (low effort, immediate benefit)

| Change | File | Estimated gain |
|---|---|---|
| Move all imports to module level | `views.py`, `campaign_views.py` | -50–200 ms on first request per worker |
| Singleton Twilio client | `views.py:291` | -50 ms per call |
| SQL aggregates in list_sessions | `views.py:746–763` | Scales with table size |
| `only()` on session list query | `views.py:732` | -30–60 ms per page load |
| Drop `session_data` JSON column | `views.py:334–343` | Fewer bytes per DB write |
