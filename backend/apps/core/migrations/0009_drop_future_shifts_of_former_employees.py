from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations


def drop_future_shifts(apps, schema_editor):
    """
    Будущие смены уволенных сотрудников — разовая уборка.

    Теперь увольнение само отменяет будущие смены. Но смены тех, кого уволили раньше,
    остались: они мешали сохранять график и выдавали уволенного за покрытие точки.
    Прошлые смены не трогаем — это история.
    """
    Shift = apps.get_model("core", "Shift")
    Store = apps.get_model("core", "Store")
    for store in Store.objects.all():
        today = datetime.now(ZoneInfo(store.timezone)).date()
        Shift.objects.filter(store=store, date__gt=today).exclude(employee__status="active").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_store_closed_weekdays"),
    ]

    operations = [
        # Обратно смены не вернуть: это уборка, откат просто ничего не делает.
        migrations.RunPython(drop_future_shifts, migrations.RunPython.noop),
    ]
