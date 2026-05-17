from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from chat.views import (
    call_status_webhook,
    initiate_call,
    list_sessions,
    outgoing_call,
    session_status,
    upload_resume,
)


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", healthcheck),
    path("health/", healthcheck),
    path("admin/", admin.site.urls),
    path("api/call/", initiate_call),

    path("api/upload-resume/", upload_resume),
    path("api/sessions/", list_sessions),
    path("api/session/<str:call_sid>/", session_status),
    path("outgoing-call/", outgoing_call),
    path("api/call-status/", call_status_webhook),
]
