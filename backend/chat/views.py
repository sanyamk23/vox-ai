import asyncio
import io
import json
import logging
import os
import re
import time
import urllib.parse
import uuid

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from twilio.rest import Client

logger = logging.getLogger(__name__)

# Strong-reference set so background tasks are not silently GC-cancelled
_BACKGROUND_TASKS: set = set()

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_JD_LENGTH = 4000
_MAX_NAME_LENGTH = 100
_MAX_RESUME_LENGTH = 8000
_MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

_ALLOWED_RESUME_MIME = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _rate_limit(key: str, max_calls: int, window_seconds: int) -> bool:
    """Atomic sliding-window rate limiter backed by Redis. Returns True if blocked."""
    slot = int(time.time() // window_seconds)
    cache_key = f"vox:rl:{key}:{slot}"
    # cache.add() is NX-only (atomic SET key 0 EX ttl) — initialises counter on first hit.
    # cache.incr() is INCR — atomic across all workers; no TOCTOU race.
    cache.add(cache_key, 0, timeout=window_seconds * 2)
    count = cache.incr(cache_key)
    return count > max_calls


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # Take the RIGHTMOST IP — appended by our own trusted proxy (nginx/ALB),
        # not forgeable by the client (unlike the leftmost, which the client controls).
        ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
        if ips:
            return ips[-1]
    return request.META.get("REMOTE_ADDR", "unknown")


def _verify_twilio_signature(request) -> bool:
    """
    Validates the X-Twilio-Signature header on inbound webhook requests.
    In production (DEBUG=False), a missing or invalid signature always returns False.
    In development, signature check is skipped when TWILIO_AUTH_TOKEN is not set.
    """
    from django.conf import settings as _settings
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

    if not auth_token:
        if _settings.DEBUG:
            logger.warning("[Security] TWILIO_AUTH_TOKEN not set — webhook signature check skipped (dev mode)")
            return True
        else:
            logger.error("[Security] TWILIO_AUTH_TOKEN not set in production — rejecting unsigned webhook")
            return False

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        public_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
        path = request.path_info.lstrip("/")
        url = f"{public_url}/{path}" if public_url else request.build_absolute_uri()
        sig = request.headers.get("X-Twilio-Signature", "")
        valid = validator.validate(url, request.POST.dict(), sig)
        if not valid:
            logger.warning("[Security] Twilio signature mismatch — url=%s sig=%s", url, sig[:20] if sig else "MISSING")
        return valid
    except Exception as exc:
        logger.error("[Security] Twilio signature check error: %s", exc)
        return False


def _check_api_key(request) -> bool:
    """
    API key guard for the sessions endpoint (candidate PII lives here).
    Only enforced when VOX_API_KEY is set — if unset, access is open.
    Key is supplied as X-Vox-Api-Key header or ?api_key= query param.
    """
    required_key = os.getenv("VOX_API_KEY", "").strip()
    if not required_key:
        return True  # Key not configured — open access
    provided = (
        request.headers.get("X-Vox-Api-Key", "")
        or request.GET.get("api_key", "")
    ).strip()
    if provided != required_key:
        logger.warning("[Security] Invalid API key from %s", _get_client_ip(request))
        return False
    return True


def _is_call_already_active(phone: str) -> bool:
    """Returns True if a call to this number was initiated within the last 60 seconds."""
    key = f"vox:active_call:{phone}"
    return bool(cache.get(key))


def _mark_call_active(phone: str) -> None:
    cache.set(f"vox:active_call:{phone}", 1, timeout=60)


def _extract_pdf_text(file_obj) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_obj.read()))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx_text(file_obj) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_obj.read()))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


@csrf_exempt
@require_http_methods(["POST"])
def upload_resume(request):
    """Parse a candidate resume (PDF or DOCX) and return extracted text."""
    if _rate_limit(f"resume:{_get_client_ip(request)}", max_calls=5, window_seconds=60):
        return JsonResponse(
            {"status": "error", "message": "Too many uploads — please wait a moment"}, status=429
        )

    file = request.FILES.get("resume")
    if not file:
        return JsonResponse(
            {"status": "error", "message": "No file provided"}, status=400
        )
    if file.size > _MAX_RESUME_BYTES:
        return JsonResponse(
            {"status": "error", "message": "File too large (max 5 MB)"}, status=400
        )

    # Validate by content-type too, not just extension
    content_type = file.content_type or ""
    fname = file.name.lower()
    is_pdf = fname.endswith(".pdf")
    is_docx = fname.endswith(".docx")
    if not (is_pdf or is_docx):
        return JsonResponse(
            {"status": "error", "message": "Only PDF and DOCX files are supported"},
            status=400,
        )
    if content_type and content_type not in _ALLOWED_RESUME_MIME and "octet-stream" not in content_type:
        logger.warning("[Resume] Rejecting mismatched content-type=%s for file=%s", content_type, fname)
        return JsonResponse(
            {"status": "error", "message": "File content-type does not match extension"}, status=400
        )

    try:
        if is_pdf:
            text = _extract_pdf_text(file)
        else:
            text = _extract_docx_text(file)
    except Exception as e:
        logger.warning("[Resume] Parse error for %s: %s", fname, e)
        return JsonResponse(
            {
                "status": "error",
                "message": "Could not parse file — try re-saving as PDF",
            },
            status=400,
        )

    if not text.strip():
        return JsonResponse(
            {
                "status": "error",
                "message": "No text found — file may be a scanned image",
            },
            status=400,
        )

    capped = text[:_MAX_RESUME_LENGTH]
    logger.info("[Resume] Extracted %d chars → capped at %d", len(text), len(capped))
    return JsonResponse({"status": "success", "text": capped, "chars": len(capped)})




def _validate_e164(number: str) -> bool:
    return bool(_E164_RE.match(number.strip()))


def _sanitize(text: str, max_length: int = 4000) -> str:
    return _SANITIZE_RE.sub("", text).strip()[:max_length]


def _clean_host(host_url: str) -> str:
    """Strip scheme for TwiML — matches FastAPI make_call()."""
    return (
        host_url.strip()
        .replace("https://", "")
        .replace("http://", "")
        .replace("wss://", "")
        .replace("ws://", "")
        .rstrip("/")
    )


def _media_stream_path(use_legacy_ws_prefix: bool = False) -> str:
    """WebSocket path segment — FastAPI uses /media-stream."""
    return "ws/media-stream" if use_legacy_ws_prefix else "media-stream"


def _build_twiml(stream_url: str) -> str:
    escaped_url = stream_url.replace("&", "&amp;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "    <Connect>\n"
        f'        <Stream url="{escaped_url}" />\n'
        "    </Connect>\n"
        "</Response>"
    )


def _place_call(
    *,
    to_number: str,
    from_number: str,
    host_url: str,
    jd: str = "Software Engineer role",
    name: str = "Candidate",
    resume_text: str = "",
    retry_num: int = 0,
    prior_transcript: list | None = None,
    prior_notes: dict | None = None,
    recruiter_inputs: dict | None = None,
    voice_id: str = "",
    use_legacy_ws_prefix: bool = False,
) -> dict:
    from .agent import DEFAULT_VOICE_ID, VOICE_PROFILES
    voice_id = voice_id if voice_id in VOICE_PROFILES else DEFAULT_VOICE_ID

    clean_host = _clean_host(host_url)
    token = str(uuid.uuid4())

    session_data: dict = {
        "jd": jd,
        "name": name,
        "phone": to_number,
        "retry_num": retry_num,
        "voice_id": voice_id,
    }
    if resume_text:
        session_data["resume_text"] = resume_text
    if prior_transcript:
        session_data["prior_transcript"] = prior_transcript
    if prior_notes:
        session_data["prior_notes"] = prior_notes
    if recruiter_inputs:
        session_data["recruiter_inputs"] = recruiter_inputs

    # Redis cache holds full session_data (including resume_text for TwilioConsumer use).
    # call_sid is added after Twilio call creation below so TwilioConsumer can pre-seed
    # the bridge with the correct call_sid before the "start" event arrives.
    stream_path = _media_stream_path(use_legacy_ws_prefix)
    # Token in PATH (not query string) — Twilio strips query params from the
    # WebSocket upgrade request but always preserves the URL path.
    stream_url = f"wss://{clean_host}/{stream_path}/{token}"
    twiml = _build_twiml(stream_url)

    logger.info("[Call] TwiML stream_url=%s", stream_url)

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not (account_sid and auth_token):
        raise RuntimeError("Twilio credentials not configured")

    client = Client(account_sid, auth_token)
    status_callback_url = f"https://{clean_host}/api/call-status/"
    call = client.calls.create(
        twiml=twiml,
        to=to_number,
        from_=from_number,
        status_callback=status_callback_url,
        status_callback_method="POST",
    )

    # Store call SID → context so the status webhook can schedule retries on no-answer.
    # recruiter_inputs MUST be stored here — it is the only way retry calls can
    # preserve the structured company/CTC/location fields the recruiter filled in.
    _mark_call_active(to_number)

    # Now that we have call.sid, inject it into session_data and cache — this lets
    # TwilioConsumer pre-seed GeminiLiveBridge with the correct call_sid so
    # finalize_gemini_session can stamp ended_at even if the Twilio "start" event
    # never arrives (e.g. WebSocket drops before media stream opens).
    session_data["call_sid"] = call.sid
    cache.set(f"vox:{token}", session_data, timeout=3600)

    cache.set(f"vox:call:{call.sid}", {
        "phone":             to_number,
        "name":              name,
        "jd":                jd,
        "resume_text":       resume_text,
        "retry_num":         retry_num,
        "host_url":          host_url,
        "from_number":       from_number,
        "prior_transcript":  prior_transcript or [],
        "prior_notes":       prior_notes or {},
        "recruiter_inputs":  recruiter_inputs or {},
        "voice_id":          voice_id,
    }, timeout=3600)

    # Pre-create a CallSession so every initiated call appears in the dashboard
    # even if the candidate never answers. finalize_gemini_session will update it.
    # Also persist session_token + session_data for Redis fallback on restart/eviction.
    # resume_text is NOT stored in session_data (it's already in the dedicated column)
    # to avoid storing PII twice in the DB permanently.
    try:
        from .models import CallSession
        db_session_data = {k: v for k, v in session_data.items() if k != "resume_text"}
        CallSession.objects.create(
            call_sid=call.sid,
            candidate_name=name,
            candidate_phone=to_number,
            job_description=jd,
            resume_text=resume_text,
            call_channel="twilio",
            session_token=token,
            session_data=db_session_data,
        )
    except Exception as _db_err:
        logger.warning("[DB] Failed to pre-create CallSession: %s", _db_err)

    return {"status": "Call initiated", "call_sid": call.sid, "stream_url": stream_url, "token": token}


@csrf_exempt
@require_http_methods(["POST"])
def outgoing_call(request):
    """
    FastAPI-compatible outbound call.
    POST /outgoing-call?to_number=...&from_number=...&host_url=...
    Body JSON also supported.
    """
    if not _check_api_key(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    if _rate_limit(f"call:{_get_client_ip(request)}", max_calls=10, window_seconds=60):
        return JsonResponse(
            {"status": "error", "message": "Too many requests — please wait a moment"}, status=429
        )

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    to_number = (
        request.GET.get("to_number") or body.get("to_number") or body.get("phone") or ""
    ).strip()
    from_number = (
        request.GET.get("from_number")
        or body.get("from_number")
        or os.getenv("TWILIO_PHONE_NUMBER", "")
    ).strip()
    host_url = (
        request.GET.get("host_url")
        or body.get("host_url")
        or os.getenv("PUBLIC_URL", "")
    ).strip()

    if not to_number:
        return JsonResponse(
            {"status": "error", "message": "to_number is required"}, status=400
        )
    if not _validate_e164(to_number):
        return JsonResponse(
            {
                "status": "error",
                "message": "to_number must be E.164 (e.g. +919876543210)",
            },
            status=400,
        )
    if not from_number:
        return JsonResponse(
            {"status": "error", "message": "from_number is required"}, status=400
        )
    if not host_url or "ngrok_url_here" in host_url:
        return JsonResponse(
            {"status": "error", "message": "host_url / PUBLIC_URL not configured"},
            status=400,
        )

    try:
        result = _place_call(
            to_number=to_number,
            from_number=from_number,
            host_url=host_url,
        )
        return JsonResponse(result)
    except Exception as e:
        logger.error("[Call-Error] %s", e)
        return JsonResponse(
            {"status": "error", "message": "Failed to initiate call"}, status=500
        )


async def _precache_interview_context(
    token: str, jd: str, name: str, recruiter_inputs: dict | None
) -> None:
    """Parse JD while the phone rings and cache the result. Fire-and-forget."""
    from .agents.manager import AgentManager
    try:
        manager = AgentManager(session_id=f"precache:{token}")
        context = await manager.prepare_session(
            jd=jd, candidate_name=name, recruiter_inputs=recruiter_inputs
        )
        await sync_to_async(cache.set, thread_sensitive=False)(f"vox:context:{token}", context.to_dict(), timeout=3600)
        logger.info("[Precache] JD context ready token=%s status=%s", token, context.recruiter_status)
    except Exception as exc:
        logger.warning("[Precache] Failed for token=%s: %s", token, exc)


@csrf_exempt
async def initiate_call(request):
    """UI outbound call — POST /api/call/ with {phone, jd, name}."""
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST allowed"}, status=405
        )

    # Rate limit: 10 call initiations per IP per minute
    client_ip = _get_client_ip(request)
    if await sync_to_async(_rate_limit)(f"call:{client_ip}", max_calls=10, window_seconds=60):
        logger.warning("[RateLimit] /api/call/ blocked for IP=%s", client_ip)
        return JsonResponse(
            {"status": "error", "message": "Too many requests — please wait a moment"}, status=429
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON body"}, status=400
        )

    try:
        to_number = (data.get("phone") or data.get("to_number") or "").strip()
        raw_jd = data.get("jd") or "Software Engineer role"
        raw_name = data.get("name") or "Candidate"

        if not to_number:
            return JsonResponse(
                {"status": "error", "message": "phone is required"}, status=400
            )
        if not _validate_e164(to_number):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "phone must be in E.164 format (e.g. +919876543210)",
                },
                status=400,
            )

        jd = _sanitize(raw_jd, _MAX_JD_LENGTH)
        name = _sanitize(raw_name, _MAX_NAME_LENGTH)
        resume_text = _sanitize(data.get("resume_text") or "", _MAX_RESUME_LENGTH)
        if not jd:
            return JsonResponse(
                {"status": "error", "message": "jd cannot be empty"}, status=400
            )

        # Structured recruiter inputs (from UI form) — sanitize each field
        raw_recruiter_inputs = data.get("recruiter_inputs") or {}
        _RECRUITER_INPUT_FIELDS = {
            "company_overview", "team_details", "company_location",
            "years_of_experience", "ctc_range", "required_joining_timeline",
            "work_location_type",
        }
        recruiter_inputs = {
            k: _sanitize(str(v), 500)
            for k, v in raw_recruiter_inputs.items()
            if k in _RECRUITER_INPUT_FIELDS and isinstance(v, str) and v.strip()
        } or None

        public_url = (data.get("host_url") or os.getenv("PUBLIC_URL", "")).strip()
        if not public_url or "ngrok_url_here" in public_url:
            return JsonResponse(
                {"status": "error", "message": "PUBLIC_URL not configured in .env"},
                status=400,
            )

        from_number = (data.get("from_number") or "").strip() or os.getenv(
            "TWILIO_PHONE_NUMBER", ""
        ).strip()
        if not from_number:
            return JsonResponse(
                {"status": "error", "message": "TWILIO_PHONE_NUMBER not configured"},
                status=500,
            )

        # Dedup: prevent double-dialling if a call to this number is still active
        if await sync_to_async(_is_call_already_active)(to_number):
            logger.warning("[Call] Duplicate call attempt to %s within 60s — rejected", to_number)
            return JsonResponse(
                {"status": "error", "message": "A call to this number is already in progress — please wait"},
                status=409,
            )

        raw_voice_id = _sanitize(data.get("voice_id") or "", 20)

        logger.info(
            "[Call] Twilio → Gemini Live | To=%s | Candidate=%s | Resume=%s | Voice=%s",
            to_number, name, bool(resume_text), raw_voice_id or "default",
        )
        result = await sync_to_async(_place_call)(
            to_number=to_number,
            from_number=from_number,
            host_url=public_url,
            jd=jd,
            name=name,
            resume_text=resume_text,
            recruiter_inputs=recruiter_inputs,
            voice_id=raw_voice_id,
        )

        # Pre-parse JD while phone rings — result will be in cache before candidate answers
        _t = asyncio.create_task(
            _precache_interview_context(result["token"], jd, name, recruiter_inputs)
        )
        _BACKGROUND_TASKS.add(_t)
        _t.add_done_callback(_BACKGROUND_TASKS.discard)

        return JsonResponse({"status": "success", "call_sid": result["call_sid"]})

    except Exception as e:
        logger.error("[Call-Error] %s", e)
        return JsonResponse(
            {"status": "error", "message": "Failed to initiate call"}, status=500
        )


initiate_outgoing_call = outgoing_call


@csrf_exempt
@require_http_methods(["POST"])
def call_status_webhook(request):
    """
    Twilio status callback — POST /api/call-status/
    Fires when an outbound call finishes.  If the candidate missed the call
    (no-answer / busy / failed), schedules a retry via CallRetryManager.
    """
    # Verify this request actually came from Twilio
    if not _verify_twilio_signature(request):
        return HttpResponse(status=403)

    from .retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY

    call_sid    = request.POST.get("CallSid", "")
    call_status = request.POST.get("CallStatus", "")

    logger.info("[CallStatus] sid=%s status=%s", call_sid, call_status)

    # Only act on missed / unreachable calls — ignore completed / in-progress
    if call_status not in ("no-answer", "busy", "failed"):
        return HttpResponse(status=204)

    # Stamp ended_at on the pre-created session so the frontend poll resolves.
    # Without this the session stays in "pending" state (202) indefinitely.
    # Idempotency: use update() which only fires if ended_at is still NULL.
    # A second webhook for the same call_sid will match 0 rows and be a no-op.
    if call_sid:
        try:
            from .models import CallSession
            from django.utils import timezone
            # Map Twilio status → canonical outcome; "failed" is a carrier error, not a busy signal.
            outcome_map = {"no-answer": "BUSY", "busy": "BUSY", "failed": "FAILED"}
            outcome = outcome_map.get(call_status, "BUSY")
            updated = CallSession.objects.filter(call_sid=call_sid, ended_at__isnull=True).update(
                ended_at=timezone.now(),
                call_outcome=outcome,
            )
            if updated == 0:
                # ended_at already set — this webhook was already processed (Twilio duplicate)
                logger.info("[CallStatus] Duplicate webhook for sid=%s — already processed, skipping retry", call_sid)
                return HttpResponse(status=204)
        except Exception as _db_err:
            logger.warning("[CallStatus] Failed to mark session ended: %s", _db_err)

    session = cache.get(f"vox:call:{call_sid}")
    if not session:
        logger.warning("[CallStatus] No session data for CallSid=%s — cannot retry", call_sid)
        # Return 500 so Twilio retries the webhook delivery (in case Redis had a transient miss)
        return HttpResponse(status=500)

    phone             = session.get("phone", "")
    name              = session.get("name", "Candidate")
    jd                = session.get("jd", "")
    resume_text       = session.get("resume_text", "")
    retry_num         = session.get("retry_num", 0)
    host_url          = session.get("host_url", "") or os.getenv("PUBLIC_URL", "")
    from_number       = session.get("from_number", "") or os.getenv("TWILIO_PHONE_NUMBER", "")
    prior_transcript  = session.get("prior_transcript", [])
    prior_notes       = session.get("prior_notes", {})
    recruiter_inputs  = session.get("recruiter_inputs") or None
    voice_id          = session.get("voice_id", "")

    if not phone or not host_url or not from_number:
        logger.warning("[CallStatus] Missing context for retry — phone=%s", phone)
        return HttpResponse(status=204)

    if retry_num >= CallRetryManager.MAX_RETRIES:
        logger.info("[CallStatus] Max retries reached for %s — no further callbacks", phone)
        CallRetryManager.clear(phone)
        return HttpResponse(status=204)

    new_retry_num = CallRetryManager.record_drop(
        phone=phone,
        name=name,
        jd=jd,
        transcript=prior_transcript,
        notes=prior_notes,
        resume_text=resume_text,
        recruiter_inputs=recruiter_inputs,
        voice_id=voice_id,
    )

    delay = RETRY_1_DELAY if new_retry_num == 1 else RETRY_2_DELAY
    logger.info(
        "[CallStatus] %s for %s — scheduling retry #%d in %.0fs",
        call_status, phone, new_retry_num, delay,
    )

    state = CallRetryManager.load(phone)
    CallRetryManager.schedule_callback(
        phone=phone,
        name=name,
        jd=jd,
        transcript=state.get("transcript", prior_transcript),
        notes=state.get("notes", prior_notes),
        resume_text=state.get("resume_text", resume_text),
        recruiter_inputs=state.get("recruiter_inputs") or recruiter_inputs,
        voice_id=state.get("voice_id", voice_id),
        retry_num=new_retry_num,
        delay_seconds=delay,
        host_url=host_url,
        from_number=from_number,
    )

    return HttpResponse(status=204)


_LIST_PAGE_SIZE = 50


@csrf_exempt
@require_http_methods(["GET"])
def list_voices(request):
    """GET /api/voices/ — return available HR voice profiles."""
    from .agent import VOICE_PROFILES
    profiles = [
        {
            "id": vp["id"],
            "display_name": vp["display_name"],
            "accent": vp["accent"],
            "description": vp["description"],
        }
        for vp in VOICE_PROFILES.values()
    ]
    return JsonResponse({"voices": profiles})


@csrf_exempt
@require_http_methods(["GET"])
def list_sessions(request):
    """GET /api/sessions/?limit=50&offset=0 — paginated list of past candidate calls."""
    if not _check_api_key(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

    from .models import CallSession

    try:
        limit  = min(int(request.GET.get("limit",  _LIST_PAGE_SIZE)), 200)
        offset = max(int(request.GET.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "limit/offset must be integers"}, status=400)

    try:
        qs = CallSession.objects.all().order_by("-created_at")
        total = qs.count()
        sessions = qs[offset : offset + limit]
    except Exception:
        return JsonResponse({"status": "error", "message": "DB unavailable"}, status=500)

    outcome_counts: dict[str, int] = {}
    compatibility_counts: dict[str, int] = {}
    total_score = 0
    score_count = 0
    total_confidence = 0.0
    confidence_count = 0
    payload = []

    for session in sessions:
        outcome = session.call_outcome or "unknown"
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

        compatibility = (
            (session.candidate_summary or {}).get("compatibility_level")
            if isinstance(session.candidate_summary, dict)
            else None
        ) or "unknown"
        compatibility_counts[compatibility] = compatibility_counts.get(compatibility, 0) + 1

        if session.intent_score is not None:
            total_score += session.intent_score
            score_count += 1

        if session.eval_confidence is not None:
            total_confidence += session.eval_confidence
            confidence_count += 1

        payload.append({
            "id": session.id,
            "call_sid": session.call_sid,
            "candidate_name": session.candidate_name,
            "candidate_phone": session.candidate_phone,
            "job_description": session.job_description,
            "resume_text": session.resume_text,
            "summary": session.summary,
            "intent_score": session.intent_score,
            "call_outcome": session.call_outcome,
            "call_channel": session.call_channel,
            "created_at": session.created_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "notes": session.notes,
            "candidate_summary": session.candidate_summary,
            "eval_confidence": session.eval_confidence,
            "dimension_scores": session.dimension_scores,
            "eval_reasoning": session.eval_reasoning,
            "transcript_length": len(session.transcript or []),
            # Full transcript is excluded from the list view — fetch /api/session/<sid>/ for it
        })

    average_score = round(total_score / score_count, 1) if score_count else None
    average_confidence = round(total_confidence / confidence_count, 2) if confidence_count else None

    return JsonResponse({
        "status": "success",
        "total_sessions": total,
        "limit": limit,
        "offset": offset,
        "outcome_counts": outcome_counts,
        "compatibility_counts": compatibility_counts,
        "average_score": average_score,
        "average_confidence": average_confidence,
        "sessions": payload,
    })


@csrf_exempt
@require_http_methods(["POST"])
def end_call(request, call_sid: str):
    """POST /api/call/<call_sid>/end/ — hang up an active Twilio call from the UI."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not (account_sid and auth_token):
        return JsonResponse({"status": "error", "message": "Twilio not configured"}, status=500)
    try:
        client = Client(account_sid, auth_token)
        client.calls(call_sid).update(status="completed")
        return JsonResponse({"status": "ok"})
    except Exception as e:
        err_str = str(e)
        logger.warning("[EndCall] %s: %s", call_sid, e)
        # Twilio error 20404 = resource not found (bad/expired call_sid)
        if "20404" in err_str or "not found" in err_str.lower():
            return JsonResponse({"status": "error", "message": "Call not found"}, status=404)
        return JsonResponse({"status": "error", "message": "Failed to end call"}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def session_status(request, call_sid: str):
    """
    GET /api/session/<call_sid>/ — poll for post-call evaluation results.
    Guarded by API key — this endpoint exposes evaluation data (notes, scores).

    A CallSession is pre-created on call initiation (no ended_at, no score).
    Returns 202 while the call is live, 200+evaluating once call ends but
    evaluation is still running, 200+complete when the DB record has ended_at set.
    Uses Redis ended marker (vox:ended:<call_sid>) to detect call end before
    the slow evaluation/DB write completes.
    """
    if not _check_api_key(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

    from .models import CallSession

    try:
        session = CallSession.objects.filter(call_sid=call_sid).order_by("-created_at").first()
    except Exception:
        return JsonResponse({"status": "error", "message": "DB unavailable"}, status=500)

    if not session:
        return JsonResponse({"status": "not_found"}, status=404)

    # Pre-created sessions have ended_at=None — call may still be live.
    if not session.ended_at:
        # Check Redis ended marker — set by disconnect() before slow DB write completes
        if cache.get(f"vox:ended:{call_sid}"):
            return JsonResponse({"status": "evaluating"})
        return JsonResponse({"status": "pending"}, status=202)

    return JsonResponse({
        "status": "complete",
        "score": session.intent_score,
        "call_outcome": session.call_outcome,
        "notes": session.notes,
        "candidate_summary": session.candidate_summary,
        "eval_confidence": session.eval_confidence,
    })
