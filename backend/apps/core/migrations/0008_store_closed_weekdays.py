from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0007_alter_employee_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='store',
            name='closed_weekdays',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
