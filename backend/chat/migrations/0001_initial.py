from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='CallSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('call_sid', models.CharField(blank=True, default='', max_length=100)),
                ('candidate_name', models.CharField(default='Candidate', max_length=200)),
                ('candidate_phone', models.CharField(blank=True, default='', max_length=20)),
                ('job_description', models.TextField(blank=True, default='')),
                ('transcript', models.JSONField(default=list)),
                ('notes', models.JSONField(default=dict)),
                ('summary', models.TextField(blank=True, default='')),
                ('intent_score', models.IntegerField(blank=True, null=True)),
                ('call_outcome', models.CharField(blank=True, default='', max_length=30)),
                ('call_channel', models.CharField(default='web', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
