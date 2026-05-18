from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0004_candidate_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='callsession',
            name='session_token',
            field=models.CharField(
                max_length=36, blank=True, default='', db_index=True,
                help_text='UUID token used as Redis key; allows DB fallback on Redis miss',
            ),
        ),
        migrations.AddField(
            model_name='callsession',
            name='session_data',
            field=models.JSONField(
                default=dict, blank=True,
                help_text='Full session payload (jd, name, phone, voice_id, etc.) for Redis fallback',
            ),
        ),
    ]
