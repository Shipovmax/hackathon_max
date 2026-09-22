import secrets

from django.db import models

from .accounts import MaxAccount
from .network import Store


class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", "Активен"
    DISMISSED = "dismissed", "Уволен"
    # Убран из списка владельцем. Запись остаётся, потому что на неё ссылаются отметки:
    # в истории задач должно быть видно, кто их закрыл.
    REMOVED = "removed", "Убран из списка"


class Employee(models.Model):
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="employees")
    name = models.CharField(max_length=150)
    account = models.OneToOneField(
        MaxAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="employee"
    )
    status = models.CharField(
        max_length=16, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InviteCode(models.Model):
    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="invites")
    code = models.CharField(max_length=16, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code

    @classmethod
    def issue(cls, employee: Employee, length: int = 8) -> "InviteCode":
        while True:
            code = "".join(secrets.choice(cls.ALPHABET) for _ in range(length))
            if not cls.objects.filter(code=code).exists():
                return cls.objects.create(employee=employee, code=code)
