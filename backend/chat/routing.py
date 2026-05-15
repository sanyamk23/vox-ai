"""
WebSocket URL routing.

Both consumers now live in consumers.py (DRY — no separate twilio_consumer.py).
"""
from django.urls import re_path
from .consumers import VoiceConsumer, TwilioConsumer

websocket_urlpatterns = [
    re_path(r"ws/voice/", VoiceConsumer.as_asgi()),
    re_path(r"ws/twilio/", TwilioConsumer.as_asgi()),
]
