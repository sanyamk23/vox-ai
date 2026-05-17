from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_resume_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='callsession',
            name='candidate_summary',
            field=models.JSONField(
                blank=True, null=True,
                help_text='Compatibility summary from SummaryAgent (green/yellow/red)',
            ),
        ),
    ]
