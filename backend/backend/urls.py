from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from chat.views import (
    create_web_session,
    initiate_call,
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
    path("api/web-session/", create_web_session),
    path("api/upload-resume/", upload_resume),
    path("api/session/<str:call_sid>/", session_status),
    path("outgoing-call/", outgoing_call),
]
