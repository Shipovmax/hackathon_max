from django.db import models

from .accounts import MaxAccount


class Network(models.Model):
    owner = models.OneToOneField(MaxAccount, on_delete=models.CASCADE, related_name="network")
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Store(models.Model):
    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)
    open_time = models.TimeField()
    close_time = models.TimeField()
    timezone = models.CharField(max_length=64, default="Europe/Moscow")
    closed_weekdays = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def is_closed_on(self, day) -> bool:
        return day.weekday() in (self.closed_weekdays or [])
