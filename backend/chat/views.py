"""
HTTP Views for Project Vox.

Handles REST endpoints (Twilio call initiation, health checks).
"""
from __future__ import annotations

import json
import logging
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.rest import Client
from urllib.parse import quote

logger = logging.getLogger("vox.views")


@csrf_exempt
def initiate_call(request):
    """
    POST /api/call/ — Trigger an outbound phone screening via Twilio.

    Body: {"phone": "+1...", "jd": "...", "name": "...", "company": "..."}
    """
    if request.method != 'POST':
        return JsonResponse(
            {"status": "error", "message": "Only POST allowed"}, status=405
        )

    try:
        data = json.loads(request.body)
        to_number = data.get('phone')
        jd = data.get('jd', 'Software Engineer role')
        name = data.get('name', 'Candidate')
        company = data.get('company', '')

        account_sid = os.getenv('TWILIO_ACCOUNT_SID', '').strip()
        auth_token = os.getenv('TWILIO_AUTH_TOKEN', '').strip()
        from_number = os.getenv('TWILIO_PHONE_NUMBER', '').strip()

        logger.info(f"[Call] SID: {account_sid[:8]}..., From: {from_number}")

        public_url = os.getenv('PUBLIC_URL', request.get_host())
        if 'ngrok_url_here' in public_url:
            return JsonResponse(
                {"status": "error", "message": "PUBLIC_URL not configured. Set your ngrok URL in .env."},
                status=400,
            )

        # Build the WebSocket URL for Twilio Media Streams
        stream_url = public_url.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/')
        if not stream_url.startswith('ws'):
            stream_url = f"wss://{stream_url}"

        full_ws_url = f"{stream_url}/ws/twilio/?jd={quote(jd)}&name={quote(name)}&company={quote(company)}"
        twiml = (
            f'<Response><Connect>'
            f'<Stream url="{full_ws_url}" />'
            f'</Connect></Response>'
        )

        logger.info(f"[Call] Initiating call to {to_number}")
        client = Client(account_sid, auth_token)
        call = client.calls.create(twiml=twiml, to=to_number, from_=from_number)

        logger.info(f"[Call] Success — SID: {call.sid}")
        return JsonResponse({"status": "success", "call_sid": call.sid})

    except Exception as e:
        logger.error(f"[Call] Failed: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
