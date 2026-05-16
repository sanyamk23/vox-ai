import json
import os
import re
import uuid

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from twilio.rest import Client

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_JD_LENGTH = 4000
_MAX_NAME_LENGTH = 100


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
    retry_num: int = 0,
    prior_transcript: list | None = None,
    prior_notes: dict | None = None,
    use_legacy_ws_prefix: bool = False,
) -> dict:
    clean_host = _clean_host(host_url)
    token = str(uuid.uuid4())

    session_data: dict = {"jd": jd, "name": name, "phone": to_number, "retry_num": retry_num}
    if prior_transcript:
        session_data["prior_transcript"] = prior_transcript
    if prior_notes:
        session_data["prior_notes"] = prior_notes

    cache.set(f"vox:{token}", session_data, timeout=3600)
    stream_path = _media_stream_path(use_legacy_ws_prefix)
    stream_url = f"wss://{clean_host}/{stream_path}?token={token}"
    twiml = _build_twiml(stream_url)

    print(f"Generated TwiML Schema:\n{twiml}")

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not (account_sid and auth_token):
        raise RuntimeError("Twilio credentials not configured")

    client = Client(account_sid, auth_token)
    call = client.calls.create(twiml=twiml, to=to_number, from_=from_number)
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
        request.GET.get("to_number")
        or body.get("to_number")
        or body.get("phone")
        or ""
    ).strip()
    from_number = (
        request.GET.get("from_number")
        or body.get("from_number")
        or os.getenv("TWILIO_PHONE_NUMBER", "")
    ).strip()
    host_url = (request.GET.get("host_url") or body.get("host_url") or os.getenv("PUBLIC_URL", "")).strip()

    if not to_number:
        return JsonResponse({"status": "error", "message": "to_number is required"}, status=400)
    if not _validate_e164(to_number):
        return JsonResponse(
            {"status": "error", "message": "to_number must be E.164 (e.g. +919876543210)"},
            status=400,
        )
    if not from_number:
        return JsonResponse({"status": "error", "message": "from_number is required"}, status=400)
    if not host_url or "ngrok_url_here" in host_url:
        return JsonResponse({"status": "error", "message": "host_url / PUBLIC_URL not configured"}, status=400)

    try:
        result = _place_call(
            to_number=to_number,
            from_number=from_number,
            host_url=host_url,
        )
        return JsonResponse(result)
    except Exception as e:
        print(f"[Call-Error] {e}")
        return JsonResponse({"status": "error", "message": "Failed to initiate call"}, status=500)


@csrf_exempt
def initiate_call(request):
    """UI outbound call — POST /api/call/ with {phone, jd, name}."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON body"}, status=400)

    try:
        to_number = (data.get("phone") or data.get("to_number") or "").strip()
        raw_jd = data.get("jd") or "Software Engineer role"
        raw_name = data.get("name") or "Candidate"

        if not to_number:
            return JsonResponse({"status": "error", "message": "phone is required"}, status=400)
        if not _validate_e164(to_number):
            return JsonResponse(
                {"status": "error", "message": "phone must be in E.164 format (e.g. +919876543210)"},
                status=400,
            )

        jd = _sanitize(raw_jd, _MAX_JD_LENGTH)
        name = _sanitize(raw_name, _MAX_NAME_LENGTH)
        if not jd:
            return JsonResponse({"status": "error", "message": "jd cannot be empty"}, status=400)

        public_url = (data.get("host_url") or os.getenv("PUBLIC_URL", "")).strip()
        if not public_url or "ngrok_url_here" in public_url:
            return JsonResponse(
                {"status": "error", "message": "PUBLIC_URL not configured in .env"},
                status=400,
            )

        from_number = (
            (data.get("from_number") or "").strip()
            or os.getenv("TWILIO_PHONE_NUMBER", "").strip()
        )
        if not from_number:
            return JsonResponse(
                {"status": "error", "message": "TWILIO_PHONE_NUMBER not configured"},
                status=500,
            )

        print(f"[Call] Twilio → Gemini Live (Sarah) | To: {to_number} | Candidate: {name}")
        result = _place_call(
            to_number=to_number,
            from_number=from_number,
            host_url=public_url,
            jd=jd,
            name=name,
        )
        return JsonResponse({"status": "success", "call_sid": result["call_sid"]})

    except Exception as e:
        print(f"[Call-Error] {e}")
        return JsonResponse({"status": "error", "message": "Failed to initiate call"}, status=500)


initiate_outgoing_call = outgoing_call
