from django.urls import re_path
from . import consumers, twilio_consumer

websocket_urlpatterns = [
    re_path(r'ws/voice/', consumers.VoiceConsumer.as_asgi()),
    re_path(r'ws/twilio/', twilio_consumer.TwilioConsumer.as_asgi()),
]
