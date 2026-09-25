from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_tasktemplate_available_from'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='status',
            field=models.CharField(choices=[('active', 'Активен'), ('dismissed', 'Уволен'), ('removed', 'Убран из списка')], default='active', max_length=16),
        ),
    ]
