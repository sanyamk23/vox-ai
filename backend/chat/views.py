from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.rest import Client
from urllib.parse import quote
import os
import json

@csrf_exempt
def initiate_call(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            to_number = data.get('phone')
            jd = data.get('jd', 'Software Engineer role')
            
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            from_number = os.getenv('TWILIO_PHONE_NUMBER')
            public_url = os.getenv('PUBLIC_URL', request.get_host())
            if 'ngrok_url_here' in public_url:
                return JsonResponse({"status": "error", "message": "Ngrok URL not set in .env. Twilio cannot reach localhost."}, status=400)
            
            # Ensure the protocol is correct and remove trailing slashes
            stream_url = public_url.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/')
            if not stream_url.startswith('ws'):
                stream_url = f"wss://{stream_url}"

            client = Client(account_sid, auth_token)
            
            # Perfect Path Construction
            full_ws_url = f"{stream_url}/ws/twilio/?jd={quote(jd)}"
            twiml = f'<Response><Connect><Stream url="{full_ws_url}" /></Connect></Response>'
            
            call = client.calls.create(
                twiml=twiml,
                to=to_number,
                from_=from_number
            )
            
            return JsonResponse({"status": "success", "call_sid": call.sid})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "error", "message": "Only POST allowed"}, status=405)
