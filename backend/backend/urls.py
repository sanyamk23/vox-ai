from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from chat.views import (
    call_status_webhook,
    end_call,
    initiate_call,
    list_sessions,
    list_voices,
    outgoing_call,
    session_status,
    upload_resume,
)


def healthcheck(request):
    # Verify DB is reachable — docker-compose healthcheck depends on this.
    # A simple SELECT 1 is enough to detect connection failures.
    try:
        from django.db import connection
        connection.ensure_connection()
    except Exception as exc:
        return JsonResponse({"status": "error", "detail": "db_unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", healthcheck),
    path("health/", healthcheck),
    path("admin/", admin.site.urls),
    path("api/call/", initiate_call),
    path("api/call/<str:call_sid>/end/", end_call),
    path("api/voices/", list_voices),
    path("api/upload-resume/", upload_resume),
    path("api/sessions/", list_sessions),
    path("api/session/<str:call_sid>/", session_status),
    path("outgoing-call/", outgoing_call),
    path("api/call-status/", call_status_webhook),
]
