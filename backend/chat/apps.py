from __future__ import annotations

import logging
import os

from django.apps import AppConfig
from django.conf import settings


logger = logging.getLogger(__name__)

# (env_var_name, is_required_in_production, hint)
_REQUIRED_ENV = [
    ("GEMINI_API_KEY", True, "Gemini Live API key — used for the recruiter persona."),
    ("TWILIO_ACCOUNT_SID", True, "Twilio SID — used to place outbound calls."),
    ("TWILIO_AUTH_TOKEN", True, "Twilio auth token."),
    ("TWILIO_PHONE_NUMBER", True, "E.164 number to dial from."),
    ("PUBLIC_URL", True, "Publicly reachable host (ngrok or domain) for Twilio Media Streams."),
    ("REDIS_URL", False, "Defaults to redis://redis:6379/0 (compose service)."),
    ("DATABASE_URL", False, "Defaults to the compose postgres service."),
]


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"

    def ready(self) -> None:
        # Validate env vars on app boot — fail fast in production.
        missing_required: list[tuple[str, str]] = []
        missing_optional: list[tuple[str, str]] = []
        for name, required, hint in _REQUIRED_ENV:
            if not os.getenv(name, "").strip():
                (missing_required if required else missing_optional).append((name, hint))

        if missing_required:
            lines = ["Missing required environment variables:"]
            for name, hint in missing_required:
                lines.append(f"  - {name}: {hint}")
            msg = "\n".join(lines)
            if settings.DEBUG:
                logger.warning("[Vox] %s\n[Vox] DEBUG=True — continuing anyway.", msg)
            else:
                raise RuntimeError(msg)

        for name, hint in missing_optional:
            logger.info("[Vox] Optional env %s not set — %s", name, hint)
