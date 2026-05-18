from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0004_candidate_summary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='callsession',
            name='call_sid',
            field=models.CharField(blank=True, db_index=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='callsession',
            name='candidate_phone',
            field=models.CharField(blank=True, db_index=True, default='', max_length=20),
        ),
        migrations.AddIndex(
            model_name='callsession',
            index=models.Index(fields=['-created_at'], name='callsession_created_at_idx'),
        ),
    ]
