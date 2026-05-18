from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0005_callsession_session_token_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='callsession',
            name='call_sid',
            field=models.CharField(max_length=100, blank=True, default='', db_index=True),
        ),
    ]
