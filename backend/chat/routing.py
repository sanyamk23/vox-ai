from django.urls import re_path
from . import twilio_consumer

_UUID_RE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

websocket_urlpatterns = [
    # Token embedded in path — Twilio strips query params but preserves the path
    re_path(rf'media-stream/(?P<token>{_UUID_RE})/?$', twilio_consumer.TwilioConsumer.as_asgi()),
    re_path(rf'ws/media-stream/(?P<token>{_UUID_RE})/?$', twilio_consumer.TwilioConsumer.as_asgi()),
    # Fallback (no token in path — legacy / dev)
    re_path(r'media-stream/?$', twilio_consumer.TwilioConsumer.as_asgi()),
    re_path(r'ws/media-stream/?$', twilio_consumer.TwilioConsumer.as_asgi()),
]
