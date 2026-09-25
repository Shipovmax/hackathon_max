from django.db import models
from django.db.models import F, Q

from .network import Store
from .people import Employee


class ShiftStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PUBLISHED = "published", "Опубликована"


class Shift(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="shifts")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="shifts")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=16, choices=ShiftStatus.choices, default=ShiftStatus.DRAFT
    )
    start_notified_at = models.DateTimeField(null=True, blank=True)
    summary_sent_at = models.DateTimeField(null=True, blank=True)
    board_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["date", "start_time"]
        indexes = [models.Index(fields=["store", "date"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="shift_end_after_start"
            )
        ]

    def __str__(self):
        return f"{self.employee} {self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"
