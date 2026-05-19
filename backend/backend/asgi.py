import os

# Must be first — before any Django or Channels import touches settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from chat.routing import websocket_urlpatterns


class _LifespanHandler:
    """Minimal ASGI lifespan handler — resumes any RUNNING campaigns on startup."""

    async def __call__(self, scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    from chat.campaign_views import resume_running_campaigns
                    await resume_running_campaigns()
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).error("[ASGI] Startup error: %s", exc)
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
    "lifespan": _LifespanHandler(),
})
