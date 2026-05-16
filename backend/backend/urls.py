from django.contrib import admin
from django.urls import path

from chat.views import initiate_call, outgoing_call

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/call/', initiate_call),
    path('outgoing-call/', outgoing_call),
]
