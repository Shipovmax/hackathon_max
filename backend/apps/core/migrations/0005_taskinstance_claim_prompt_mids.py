from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_shift_board_sent_at_tasktemplate_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskinstance',
            name='claim_prompt_mids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
