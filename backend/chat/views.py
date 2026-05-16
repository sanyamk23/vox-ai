import json
import os
import re
from urllib.parse import quote

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# ------------------------------------------------------------------
# Security constants
# ------------------------------------------------------------------

# E.164: + followed by 7-15 digits
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

# Strip control characters and characters that could cause injection
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_MAX_JD_LENGTH = 4000       # ~3x a typical JD; prevents prompt-stuffing
_MAX_NAME_LENGTH = 100


def _validate_e164(number: str) -> bool:
    """Strict E.164 phone validation. Prevents malformed numbers reaching Twilio."""
    return bool(_E164_RE.match(number.strip()))


def _sanitize(text: str, max_length: int = 4000) -> str:
    """Remove control characters and hard-limit length."""
    return _SANITIZE_RE.sub("", text).strip()[:max_length]


# ------------------------------------------------------------------
# View
# ------------------------------------------------------------------

@csrf_exempt
def initiate_call(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON body"}, status=400)

    try:
        to_number = (data.get("phone") or "").strip()
        raw_jd = data.get("jd") or "Software Engineer role"
        raw_name = data.get("name") or "Candidate"

        # --- Security: validate inputs before any external call ---
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

        # --- Build WebSocket URL ---
        public_url = os.getenv("PUBLIC_URL", "").strip()
        if not public_url or "ngrok_url_here" in public_url:
            return JsonResponse(
                {"status": "error", "message": "PUBLIC_URL not configured in .env"},
                status=400,
            )

        stream_url = (
            public_url
            .replace("https://", "wss://")
            .replace("http://", "ws://")
            .rstrip("/")
        )
        if not stream_url.startswith("ws"):
            stream_url = f"wss://{stream_url}"

        ws_url = (
            f"{stream_url}/ws/twilio/"
            f"?jd={quote(jd)}&name={quote(name)}&phone={quote(to_number)}"
        )
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Connect><Stream url="{ws_url}" /></Connect></Response>'
        )

        # --- Provider selection: SignalWire (if configured) else Twilio ---
        sw_project = os.getenv("SIGNALWIRE_PROJECT_ID", "").strip()
        sw_token = os.getenv("SIGNALWIRE_TOKEN", "").strip()
        sw_space = os.getenv("SIGNALWIRE_SPACE", "").strip()

        if sw_project and sw_token and sw_space:
            from signalwire.rest import Client as SWClient
            client = SWClient(sw_project, sw_token, signalwire_space_url=sw_space)
            from_number = os.getenv("SIGNALWIRE_PHONE_NUMBER", "").strip()
            print(f"[Call] Provider: SignalWire | To: {to_number} | Candidate: {name}")
        else:
            from twilio.rest import Client
            account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
            auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
            from_number = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
            if not (account_sid and auth_token and from_number):
                return JsonResponse(
                    {"status": "error", "message": "Twilio credentials not configured"},
                    status=500,
                )
            client = Client(account_sid, auth_token)
            print(f"[Call] Provider: Twilio | To: {to_number} | Candidate: {name}")

        call = client.calls.create(twiml=twiml, to=to_number, from_=from_number)
        return JsonResponse({"status": "success", "call_sid": call.sid})

    except Exception as e:
        # Never expose internal stack traces to the client
        print(f"[Call-Error] {e}")
        return JsonResponse({"status": "error", "message": "Failed to initiate call"}, status=500)
