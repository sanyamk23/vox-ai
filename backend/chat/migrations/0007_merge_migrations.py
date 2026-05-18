from django.db import migrations


class Migration(migrations.Migration):
    """
    Merge migration — resolves two parallel branches that both forked from 0004:
      - 0005_indexes: db_index on call_sid/candidate_phone + created_at index
      - 0006_callsession_call_sid_index: db_index on call_sid (via session_token branch)
    Both branches are safe to apply together; the duplicate AlterField on call_sid is idempotent.
    """

    dependencies = [
        ('chat', '0005_indexes'),
        ('chat', '0006_callsession_call_sid_index'),
    ]

    operations = []
