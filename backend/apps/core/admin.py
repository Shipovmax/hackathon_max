from django.contrib import admin

from . import models


@admin.register(models.MaxAccount)
class MaxAccountAdmin(admin.ModelAdmin):
    list_display = ("max_user_id", "first_name", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("max_user_id", "first_name")


@admin.register(models.Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")


@admin.register(models.Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "network", "open_time", "close_time", "timezone", "is_active")
    list_filter = ("network", "is_active")


@admin.register(models.Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "account", "status")
    list_filter = ("store", "status")


@admin.register(models.InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "employee", "created_at", "used_at")


@admin.register(models.Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("store", "employee", "date", "start_time", "end_time", "status")
    list_filter = ("store", "status", "date")


@admin.register(models.TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "title", "store", "kind", "planned_time", "on_date",
        "tolerance_minutes", "requires_photo", "requires_claim", "is_active",
    )
    list_filter = ("store", "kind", "is_active")


@admin.register(models.TaskInstance)
class TaskInstanceAdmin(admin.ModelAdmin):
    list_display = ("template", "date", "status")
    list_filter = ("status", "date", "template__store")


@admin.register(models.Completion)
class CompletionAdmin(admin.ModelAdmin):
    list_display = ("instance", "employee", "completed_at", "late_minutes")


@admin.register(models.Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("instance", "employee", "claimed_at")
