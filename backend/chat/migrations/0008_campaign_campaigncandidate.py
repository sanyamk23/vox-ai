from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0007_merge_migrations'),
    ]

    operations = [
        migrations.CreateModel(
            name='Campaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('job_description', models.TextField(blank=True, default='')),
                ('voice_id', models.CharField(default='priya', max_length=50)),
                ('delay_seconds', models.IntegerField(default=30)),
                ('max_retries', models.IntegerField(default=1)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('running', 'Running'), ('paused', 'Paused'), ('completed', 'Completed')],
                    default='draft', max_length=20,
                )),
                ('total_uploaded', models.IntegerField(default=0)),
                ('valid_count', models.IntegerField(default=0)),
                ('invalid_count', models.IntegerField(default=0)),
                ('duplicate_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CampaignCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='candidates',
                    to='chat.campaign',
                )),
                ('name', models.CharField(max_length=200)),
                ('phone', models.CharField(max_length=20)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('calling', 'Calling'), ('completed', 'Completed'), ('failed', 'Failed')],
                    default='pending', max_length=20,
                )),
                ('call_sid', models.CharField(blank=True, default='', max_length=100)),
                ('call_duration', models.IntegerField(default=0)),
                ('call_outcome', models.CharField(blank=True, default='', max_length=50)),
                ('transcript', models.JSONField(default=list)),
                ('notes', models.JSONField(default=dict)),
                ('ai_summary', models.TextField(blank=True, default='')),
                ('interest_level', models.CharField(blank=True, default='', max_length=30)),
                ('retry_count', models.IntegerField(default=0)),
                ('is_valid', models.BooleanField(default=True)),
                ('is_duplicate', models.BooleanField(default=False)),
                ('validation_error', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('called_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
