from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_shift_start_notified_at_shift_summary_sent_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskinstance',
            name='final_reminder_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
