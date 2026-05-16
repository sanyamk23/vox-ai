from django.contrib import admin
from .models import CallSession


@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = ("candidate_name", "candidate_phone", "call_outcome", "intent_score", "call_channel", "created_at")
    list_filter = ("call_outcome", "call_channel")
    search_fields = ("candidate_name", "candidate_phone", "call_sid")
    readonly_fields = ("created_at", "ended_at", "transcript", "notes")
    ordering = ("-created_at",)
