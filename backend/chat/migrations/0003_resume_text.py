from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_eval_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='callsession',
            name='resume_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
