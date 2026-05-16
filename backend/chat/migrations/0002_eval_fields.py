from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='callsession',
            name='interview_context',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Parsed JD intelligence from RecruiterAgent',
            ),
        ),
        migrations.AddField(
            model_name='callsession',
            name='dimension_scores',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Per-dimension scores from EvaluationAgent',
            ),
        ),
        migrations.AddField(
            model_name='callsession',
            name='eval_confidence',
            field=models.FloatField(
                blank=True,
                null=True,
                help_text='Overall confidence (0-1) that the evaluation is accurate',
            ),
        ),
        migrations.AddField(
            model_name='callsession',
            name='eval_reasoning',
            field=models.TextField(
                blank=True,
                default='',
                help_text='EvaluationAgent reasoning for the intent score and outcome',
            ),
        ),
    ]
