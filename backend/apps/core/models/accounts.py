from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Владелец"
    EMPLOYEE = "employee", "Сотрудник"


class MaxAccount(models.Model):
    max_user_id = models.BigIntegerField(unique=True)
    dialog_chat_id = models.BigIntegerField(null=True, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    is_authenticated = True
    is_anonymous = False

    def __str__(self):
        return f"{self.first_name or 'user'} ({self.max_user_id})"
