from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_taskinstance_final_reminder_sent_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='shift',
            name='board_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasktemplate',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
