from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='shift',
            name='start_notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='shift',
            name='summary_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
