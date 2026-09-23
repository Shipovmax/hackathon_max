from datetime import time

from django.db import migrations, models

# Насколько раньше планового времени задачу можно отметить у шаблонов, заведённых
# до появления поля. Полчаса — запас на «открылись чуть раньше», но не на «закрыл
# магазин в обед».
DEFAULT_LEAD_MINUTES = 30


def earlier(value: time, minutes: int) -> time:
    """Время минус минуты, без перехода через полночь."""
    shifted = value.hour * 60 + value.minute - minutes
    return time.min if shifted <= 0 else time(shifted // 60, shifted % 60)


def fill_available_from(apps, schema_editor):
    TaskTemplate = apps.get_model("core", "TaskTemplate")
    for template in TaskTemplate.objects.all().iterator():
        TaskTemplate.objects.filter(pk=template.pk).update(
            available_from=earlier(template.planned_time, DEFAULT_LEAD_MINUTES)
        )


def drop_available_from(apps, schema_editor):
    """Обратная миграция ничего не восстанавливает: поле просто исчезает."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_taskinstance_claim_prompt_mids"),
    ]

    operations = [
        migrations.AddField(
            model_name="tasktemplate",
            name="available_from",
            field=models.TimeField(null=True),
        ),
        migrations.RunPython(fill_available_from, drop_available_from),
        migrations.AlterField(
            model_name="tasktemplate",
            name="available_from",
            field=models.TimeField(default=time.min),
        ),
    ]
