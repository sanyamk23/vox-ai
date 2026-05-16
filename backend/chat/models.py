from django.db import models


class CallSession(models.Model):
    call_sid = models.CharField(max_length=100, blank=True, default='')
    candidate_name = models.CharField(max_length=200, default='Candidate')
    candidate_phone = models.CharField(max_length=20, blank=True, default='')
    job_description = models.TextField(blank=True, default='')
    resume_text = models.TextField(blank=True, default='')
    transcript = models.JSONField(default=list)
    notes = models.JSONField(default=dict)
    summary = models.TextField(blank=True, default='')
    intent_score = models.IntegerField(null=True, blank=True)
    call_outcome = models.CharField(max_length=30, blank=True, default='')
    call_channel = models.CharField(max_length=20, default='web')
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Agent-layer fields (populated when AgentManager is active)
    interview_context = models.JSONField(
        default=dict, blank=True,
        help_text="Parsed JD intelligence from RecruiterAgent"
    )
    dimension_scores = models.JSONField(
        null=True, blank=True,
        help_text="Per-dimension scores from EvaluationAgent"
    )
    eval_confidence = models.FloatField(
        null=True, blank=True,
        help_text="Overall confidence (0-1) that the evaluation is accurate"
    )
    eval_reasoning = models.TextField(
        blank=True, default='',
        help_text="EvaluationAgent reasoning for the intent score and outcome"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.candidate_name} | {self.call_outcome} | {self.created_at:%Y-%m-%d %H:%M}"
