from django.db import models
from django.db.models import Q

from .network import Store
from .people import Employee


class TaskKind(models.TextChoices):
    DAILY = "daily", "Ежедневная"
    ONE_TIME = "one_time", "Разовая на дату"


class TaskStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Запланирована"
    REMINDED = "reminded", "Напоминание отправлено"
    AWAITING_PHOTO = "awaiting_photo", "Ожидает фото"
    DONE_ON_TIME = "done_on_time", "Выполнена вовремя"
    DONE_LATE = "done_late", "Выполнена с опозданием"
    OVERDUE = "overdue", "Просрочена"
    UNCLAIMED = "unclaimed", "Никто не взял"
    MISSED = "missed", "Не выполнена за смену"


class TaskTemplate(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="task_templates")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=TaskKind.choices, default=TaskKind.DAILY)
    planned_time = models.TimeField()
    on_date = models.DateField(null=True, blank=True)
    tolerance_minutes = models.PositiveSmallIntegerField(default=15)
    requires_photo = models.BooleanField(default=True)
    requires_claim = models.BooleanField(default=False)
    photo_prompt = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    # По этой отметке планировщик видит, что владелец правил задачи точки среди дня,
    # и рассылает смене обновлённый список. Снятие галочки «активна» тоже её двигает.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["planned_time"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="daily", on_date__isnull=True)
                    | Q(kind="one_time", on_date__isnull=False)
                ),
                name="task_template_date_matches_kind",
            )
        ]

    def __str__(self):
        return self.title


class TaskInstance(models.Model):
    template = models.ForeignKey(TaskTemplate, on_delete=models.PROTECT, related_name="instances")
    date = models.DateField()
    status = models.CharField(
        max_length=16, choices=TaskStatus.choices, default=TaskStatus.SCHEDULED
    )
    # Два напоминания перед сроком: первое за REMINDER_FIRST_MINUTES_BEFORE, последнее за
    # REMINDER_FINAL_MINUTES_BEFORE. Отметки нужны, чтобы тик планировщика не слал их повторно.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    final_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    escalation_sent_at = models.DateTimeField(null=True, blank=True)
    overdue_notified_at = models.DateTimeField(null=True, blank=True)
    closing_notified_at = models.DateTimeField(null=True, blank=True)
    awaiting_photo_employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    awaiting_photo_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date", "template__planned_time"]
        constraints = [
            models.UniqueConstraint(fields=["template", "date"], name="uniq_task_instance_per_day")
        ]

    def __str__(self):
        return f"{self.template} {self.date}"


class Completion(models.Model):
    instance = models.OneToOneField(
        TaskInstance, on_delete=models.CASCADE, related_name="completion"
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="completions")
    completed_at = models.DateTimeField()
    late_minutes = models.PositiveIntegerField(default=0)
    photo = models.FileField(upload_to="completions/%Y/%m/%d/", blank=True)
    photo_token = models.CharField(max_length=512, blank=True)


class Claim(models.Model):
    instance = models.OneToOneField(TaskInstance, on_delete=models.CASCADE, related_name="claim")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="claims")
    claimed_at = models.DateTimeField(auto_now_add=True)
