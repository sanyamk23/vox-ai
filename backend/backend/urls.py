from django.contrib import admin
from django.urls import path

from chat.views import initiate_call, outgoing_call, session_status, upload_resume

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/call/', initiate_call),
    path('api/upload-resume/', upload_resume),
    path('api/session/<str:call_sid>/', session_status),
    path('outgoing-call/', outgoing_call),
]
