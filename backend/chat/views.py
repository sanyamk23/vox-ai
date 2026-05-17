import io
import json
import logging
import os
import re
import urllib.parse
import uuid

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from twilio.rest import Client

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_JD_LENGTH = 4000
_MAX_NAME_LENGTH = 100
_MAX_RESUME_LENGTH = 8000
_MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB


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
    file = request.FILES.get("resume")
    if not file:
        return JsonResponse(
            {"status": "error", "message": "No file provided"}, status=400
        )
    if file.size > _MAX_RESUME_BYTES:
        return JsonResponse(
            {"status": "error", "message": "File too large (max 5 MB)"}, status=400
        )

    fname = file.name.lower()
    try:
        if fname.endswith(".pdf"):
            text = _extract_pdf_text(file)
        elif fname.endswith(".docx"):
            text = _extract_docx_text(file)
        else:
            return JsonResponse(
                {"status": "error", "message": "Only PDF and DOCX files are supported"},
                status=400,
            )
    except Exception as e:
        print(f"[Resume] Parse error: {e}")
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
    print(f"[Resume] Extracted {len(text)} chars → capped at {len(capped)}")
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
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "    <Connect>\n"
        f'        <Stream url="{stream_url}" />\n'
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
    use_legacy_ws_prefix: bool = False,
) -> dict:
    clean_host = _clean_host(host_url)
    token = str(uuid.uuid4())

    session_data: dict = {
        "jd": jd,
        "name": name,
        "phone": to_number,
        "retry_num": retry_num,
    }
    if resume_text:
        session_data["resume_text"] = resume_text
    if prior_transcript:
        session_data["prior_transcript"] = prior_transcript
    if prior_notes:
        session_data["prior_notes"] = prior_notes
    if recruiter_inputs:
        session_data["recruiter_inputs"] = recruiter_inputs

    cache.set(f"vox:{token}", session_data, timeout=3600)
    stream_path = _media_stream_path(use_legacy_ws_prefix)
    # Embed name + phone in the URL so the consumer always has them as a
    # fallback even if the Redis cache misses on WebSocket connect
    stream_url = (
        f"wss://{clean_host}/{stream_path}"
        f"?token={token}"
        f"&name={urllib.parse.quote(name, safe='')}"
        f"&phone={urllib.parse.quote(to_number, safe='')}"
    )
    twiml = _build_twiml(stream_url)

    print(f"Generated TwiML Schema:\n{twiml}")

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

    # Store call SID → context so the status webhook can schedule retries on no-answer
    cache.set(f"vox:call:{call.sid}", {
        "phone":            to_number,
        "name":             name,
        "jd":               jd,
        "resume_text":      resume_text,
        "retry_num":        retry_num,
        "host_url":         host_url,
        "from_number":      from_number,
        "prior_transcript": prior_transcript or [],
        "prior_notes":      prior_notes or {},
    }, timeout=3600)

    return {"status": "Call initiated", "call_sid": call.sid, "stream_url": stream_url}


@csrf_exempt
@require_http_methods(["POST"])
def outgoing_call(request):
    """
    FastAPI-compatible outbound call.
    POST /outgoing-call?to_number=...&from_number=...&host_url=...
    Body JSON also supported.
    """
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
        print(f"[Call-Error] {e}")
        return JsonResponse(
            {"status": "error", "message": "Failed to initiate call"}, status=500
        )


@csrf_exempt
def initiate_call(request):
    """UI outbound call — POST /api/call/ with {phone, jd, name}."""
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Only POST allowed"}, status=405
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

        print(
            f"[Call] Twilio → Gemini Live | To: {to_number} | Candidate: {name} | Resume: {bool(resume_text)}"
        )
        result = _place_call(
            to_number=to_number,
            from_number=from_number,
            host_url=public_url,
            jd=jd,
            name=name,
            resume_text=resume_text,
            recruiter_inputs=recruiter_inputs,
        )
        return JsonResponse({"status": "success", "call_sid": result["call_sid"]})

    except Exception as e:
        print(f"[Call-Error] {e}")
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
    from .retry_manager import CallRetryManager, RETRY_1_DELAY, RETRY_2_DELAY

    call_sid    = request.POST.get("CallSid", "")
    call_status = request.POST.get("CallStatus", "")

    logger.info("[CallStatus] sid=%s status=%s", call_sid, call_status)

    # Only act on missed / unreachable calls — ignore completed / in-progress
    if call_status not in ("no-answer", "busy", "failed"):
        return HttpResponse(status=204)

    session = cache.get(f"vox:call:{call_sid}")
    if not session:
        logger.warning("[CallStatus] No session data for CallSid=%s — cannot retry", call_sid)
        return HttpResponse(status=204)

    phone       = session.get("phone", "")
    name        = session.get("name", "Candidate")
    jd          = session.get("jd", "")
    resume_text = session.get("resume_text", "")
    retry_num   = session.get("retry_num", 0)
    host_url    = session.get("host_url", "") or os.getenv("PUBLIC_URL", "")
    from_number = session.get("from_number", "") or os.getenv("TWILIO_PHONE_NUMBER", "")
    prior_transcript = session.get("prior_transcript", [])
    prior_notes      = session.get("prior_notes", {})

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
        retry_num=new_retry_num,
        delay_seconds=delay,
        host_url=host_url,
        from_number=from_number,
    )

    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["GET"])
def list_sessions(request):
    """GET /api/sessions/ — return an analytics-aware list of past candidate calls."""
    from .models import CallSession

    try:
        sessions = CallSession.objects.all().order_by("-created_at")
    except Exception:
        return JsonResponse({"status": "error", "message": "DB unavailable"}, status=500)

    outcome_counts = {}
    compatibility_counts = {}
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
            "transcript": session.transcript,
        })

    average_score = round(total_score / score_count, 1) if score_count else None
    average_confidence = round(total_confidence / confidence_count, 2) if confidence_count else None

    return JsonResponse({
        "status": "success",
        "total_sessions": len(payload),
        "outcome_counts": outcome_counts,
        "compatibility_counts": compatibility_counts,
        "average_score": average_score,
        "average_confidence": average_confidence,
        "sessions": payload,
    })


@csrf_exempt
@require_http_methods(["GET"])
def session_status(request, call_sid: str):
    """
    GET /api/session/<call_sid>/ — poll for post-call evaluation results.
    Returns 202 while evaluation is still running, 200 when complete.
    """
    from .models import CallSession

    try:
        session = CallSession.objects.filter(call_sid=call_sid).order_by("-created_at").first()
    except Exception:
        return JsonResponse({"status": "error", "message": "DB unavailable"}, status=500)

    if not session:
        return JsonResponse({"status": "pending"}, status=202)

    return JsonResponse({
        "status": "complete",
        "score": session.intent_score,
        "call_outcome": session.call_outcome,
        "notes": session.notes,
        "candidate_summary": session.candidate_summary,
        "eval_confidence": session.eval_confidence,
    })
