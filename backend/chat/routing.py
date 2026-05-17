from django.urls import re_path
from . import twilio_consumer

websocket_urlpatterns = [

    # FastAPI-compatible path (wss://host/media-stream)
    re_path(r'media-stream/?', twilio_consumer.TwilioConsumer.as_asgi()),
    # Legacy alias
    re_path(r'ws/media-stream/?', twilio_consumer.TwilioConsumer.as_asgi()),
]
