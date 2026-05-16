from django.db import models


class CallSession(models.Model):
    call_sid = models.CharField(max_length=100, blank=True, default='')
    candidate_name = models.CharField(max_length=200, default='Candidate')
    candidate_phone = models.CharField(max_length=20, blank=True, default='')
    job_description = models.TextField(blank=True, default='')
    transcript = models.JSONField(default=list)
    notes = models.JSONField(default=dict)
    summary = models.TextField(blank=True, default='')
    intent_score = models.IntegerField(null=True, blank=True)
    call_outcome = models.CharField(max_length=30, blank=True, default='')
    call_channel = models.CharField(max_length=20, default='web')
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.candidate_name} | {self.call_outcome} | {self.created_at:%Y-%m-%d %H:%M}"
