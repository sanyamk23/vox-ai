from django.contrib import admin
from django.urls import path
from chat.views import initiate_call

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/call/', initiate_call),
]
