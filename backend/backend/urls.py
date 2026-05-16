from django.contrib import admin
from django.urls import path

from chat.views import initiate_call, outgoing_call, upload_resume

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/call/', initiate_call),
    path('api/upload-resume/', upload_resume),
    path('outgoing-call/', outgoing_call),
]
