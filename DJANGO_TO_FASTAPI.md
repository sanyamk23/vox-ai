# Django → FastAPI Migration Analysis

This document is an honest assessment of what it would take to migrate this backend from Django + Django Channels to FastAPI + Uvicorn, based on the actual codebase.

**Short answer:** It's doable but not trivial. Estimated 3–5 weeks of focused engineering. The WebSocket consumer and ORM are the hardest parts. The actual gain in this app is moderate because the real latency is in Gemini and Twilio, not in Django's overhead.

---

## What you'd actually gain

| Gain | How much it matters here |
|---|---|
| Faster cold start (no Django app registry) | Low — already using Daphne ASGI, cold start is dominated by Gemini |
| Async-native ORM (SQLAlchemy async or Tortoise) | Medium — removes `sync_to_async` overhead on every DB call |
| Less framework magic / easier to read | Subjective |
| Smaller Docker image | Low — Python dependencies dominate, not Django itself |
| Pydantic validation on request bodies | Low — current app mostly handles raw POST/multipart |

**What you wouldn't gain:** FastAPI doesn't make Gemini Live faster, doesn't remove the Twilio round-trip, and doesn't eliminate the audio resampling cost. Those dominate the latency budget.

---

## Component-by-component difficulty

### 1. Django ORM → SQLAlchemy async (Hard)

**Affected files:** `models.py`, `views.py`, `campaign_views.py`, `agent.py`, `twilio_consumer.py`

Every `Campaign.objects.get(...)`, `CallSession.objects.create(...)`, `CampaignCandidate.objects.filter(...).first()` must be rewritten. There are ~60 ORM call sites across the codebase.

The current models translate roughly like this:

```python
# Django (current)
class Campaign(models.Model):
    name = models.CharField(max_length=200)
    status = models.CharField(choices=STATUS_CHOICES, default=DRAFT)
    delay_seconds = models.IntegerField(default=30)
    ...

# SQLAlchemy async equivalent
class Campaign(Base):
    __tablename__ = "campaign"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    delay_seconds: Mapped[int] = mapped_column(default=30)
```

And every query:
```python
# Django (current)
campaign = await sync_to_async(Campaign.objects.get)(id=campaign_id)

# SQLAlchemy async
async with AsyncSession(engine) as session:
    campaign = await session.get(Campaign, campaign_id)
```

Also affected: the `Campaign.stats` property (which runs 6 queryset filters) would need to become a separate async method or a single SQL query.

**There are 9 Django migrations** that must be converted to Alembic. The schema history can be preserved by pointing Alembic at the existing DB and auto-generating from the current state — you don't need to replay all 9 migration steps.

**Effort: ~40–50 hours**

---

### 2. Django Channels WebSocket Consumer → FastAPI WebSocket (Hard)

**Affected file:** `twilio_consumer.py` (318 lines, `TwilioConsumer` class)

This is the most structurally different part. Django Channels gives you:

```python
class TwilioConsumer(AsyncWebsocketConsumer):
    async def connect(self): ...
    async def disconnect(self, code): ...
    async def receive(self, text_data=None, bytes_data=None): ...
```

FastAPI's WebSocket is a route, not a class:

```python
@app.websocket("/media-stream/{token}")
async def twilio_ws(websocket: WebSocket, token: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            ...
    except WebSocketDisconnect:
        ...
```

The key things you lose and must manually implement:
- `self.channel_name` — Channels assigns a unique ID per connection. In FastAPI, generate a UUID at connect time.
- `self.scope` — Contains the WebSocket headers and path. In FastAPI, use `websocket.headers` and `websocket.path_params`.
- `self.accept()`, `self.send()`, `self.close()` — Direct equivalents exist in FastAPI (`websocket.accept()`, `websocket.send_text()`, `websocket.close()`).
- The `GeminiRecruiter` lifecycle (start/stop/audio pump) is not Channels-specific — it's just Python. It ports directly without changes.

The actual logic inside `connect/disconnect/receive` translates almost line for line. The hardest part is untangling the Django Channels class structure, not rewriting logic.

**Effort: ~20–25 hours**

---

### 3. URL routing (Easy)

**Affected files:** `urls.py`, `backend/urls.py`

Django:
```python
urlpatterns = [
    path("api/call/", views.initiate_call),
    path("api/campaigns/<int:campaign_id>/start/", campaign_views.start_campaign),
]
```

FastAPI:
```python
@app.post("/api/call/")
async def initiate_call(request: Request): ...

@app.post("/api/campaigns/{campaign_id}/start/")
async def start_campaign(campaign_id: int): ...
```

One-to-one replacement. No logic changes.

**Effort: ~3–4 hours**

---

### 4. Middleware (Easy–Medium)

Current Django middleware stack:

| Django middleware | FastAPI equivalent |
|---|---|
| `CorsMiddleware` | `fastapi.middleware.cors.CORSMiddleware` (identical config) |
| `SecurityMiddleware` | Set headers manually or use `starlette.middleware.trustedhost` |
| `WhiteNoiseMiddleware` | `app.mount("/static", StaticFiles(...))` |
| `SessionMiddleware` | Not needed — this app has no user sessions |
| `CsrfViewMiddleware` | Not needed — stateless API, `@csrf_exempt` everywhere anyway |
| `AuthenticationMiddleware` | Not needed — no Django auth is enforced currently |

Most of the middleware stack is effectively already bypassed (`@csrf_exempt` on every view, no auth enforced). FastAPI would be cleaner by simply not including what isn't used.

**Effort: ~4–6 hours**

---

### 5. Django Admin (Low effort to drop, medium to replace)

**Affected file:** `admin.py`

The Django admin at `/admin/` gives a UI to browse `CallSession` records. This is useful for debugging.

Options:
- **Drop it** — Access the DB directly with `psql` or a DB GUI (DBeaver, TablePlus). Zero migration effort.
- **Replace with FastAPI + a simple admin package** (`fastapi-admin`, `SQLAdmin`) — ~10–15 hours to set up.
- **Keep a minimal Django app just for admin** — Not recommended (two frameworks in one codebase).

---

### 6. ASGI server: Daphne → Uvicorn (Trivial)

Current `entrypoint.sh`:
```bash
exec daphne -b 0.0.0.0 -p 8000 backend.asgi:application
```

FastAPI:
```bash
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Uvicorn is already the industry standard for FastAPI. No behaviour change. Single-worker is correct here because the app is async and uses a persistent Gemini WebSocket connection per call.

**Effort: ~1 hour**

---

### 7. Static files (Trivial)

`collectstatic` and WhiteNoise serve Django's admin CSS/JS. Without Django admin, there are no static files to serve. The frontend is a separate Vite container anyway.

**Effort: ~0 hours**

---

### 8. Settings → Pydantic config (Easy)

`backend/settings.py` contains ~200 lines of Django config. Most of it is boilerplate (`INSTALLED_APPS`, `TEMPLATES`, etc.) that simply disappears with FastAPI. What remains:

```python
# settings.py things that map to FastAPI
SECRET_KEY → unused (no Django sessions/signing)
DATABASE_URL → SQLAlchemy engine string
REDIS_URL → Redis client init
ALLOWED_HOSTS → CORS config
CORS_ALLOWED_ORIGINS → CORSMiddleware
LOGGING → identical Python logging config
```

Use Pydantic's `BaseSettings`:
```python
class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    cors_origins: list[str] = ["*"]
    ...
    model_config = SettingsConfigDict(env_file=".env")
```

**Effort: ~3–4 hours**

---

## What does NOT need to change

These parts of the codebase are framework-agnostic and port with zero or near-zero changes:

| Component | Reason |
|---|---|
| `gemini_recruiter.py` | Pure Python async, no Django imports |
| `agent.py` (evaluation logic) | Pure Python, no Django imports except `CallSession` DB write at the end |
| `retry_manager.py` | Pure Python + Redis |
| Audio resampling (`audioop`) | Pure Python stdlib |
| Twilio TwiML building (`_build_twiml`) | Pure Python |
| All environment variable reads (`os.getenv`) | Framework-agnostic |
| Redis cache reads/writes | Use `redis-py` directly instead of `django.core.cache` — same API |
| Campaign logic (loop, delay, task management) | Pure asyncio |

The core AI and telephony logic — which is the hard and valuable part — is already cleanly separated from Django.

---

## Migration path if you decide to do it

A big-bang rewrite is risky. The safer path:

**Phase 1 (1 week):** Set up FastAPI skeleton alongside Django. Migrate DB models to SQLAlchemy, run both ORMs against the same Postgres DB. Write Alembic config pointed at existing schema.

**Phase 2 (1 week):** Migrate read-only endpoints first (`/api/voices/`, `/api/sessions/`, `/api/campaigns/`). These are stateless and easy to validate.

**Phase 3 (1–2 weeks):** Migrate the WebSocket consumer (`/media-stream/{token}`). This is the riskiest — test against Twilio staging before cutting over.

**Phase 4 (3–5 days):** Migrate remaining write endpoints (`/api/call/`, `/api/campaigns/*/start/`, webhooks). Cut over DNS.

**Phase 5 (2–3 days):** Remove Django entirely. Clean up.

---

## Honest recommendation

**Don't migrate right now.** The biggest latency wins (Gemini cold-start, Twilio client singleton, SQL aggregates, module-level imports) are all achievable within the current Django setup — see `LATENCY_IMPROVEMENTS.md`. Those changes take days, not weeks, and deliver most of the benefit.

FastAPI becomes worth the effort if:
- The app needs to handle 50+ concurrent calls (Django Channels is fine up to ~20 with a single Daphne worker)
- You want async-native ORM without `sync_to_async` noise (legitimate reason)
- The team is more comfortable with FastAPI's explicit style

The core AI and telephony code is already framework-agnostic. A migration would be mostly boilerplate replacement, not fundamental rearchitecting. But it's still 3–5 weeks of work that doesn't change what the user hears on the call.
