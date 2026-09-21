from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import TaskKind, TaskTemplate

from ..presenters import template_item
from ..scoping import (
    bad_request,
    clean_bool,
    clean_text,
    get_store,
    get_template,
    parse_date,
    parse_time,
)

DEFAULTS = {
    "kind": TaskKind.DAILY,
    "on_date": None,
    "tolerance_minutes": 15,
    "requires_photo": True,
    "requires_claim": False,
}


def clean_template(values: dict) -> dict:
    """Validate a complete set of template fields, whether it comes from POST or from a merged PATCH."""
    kind = values.get("kind")
    if kind not in TaskKind.values:
        raise bad_request("Тип задачи: ежедневная или разовая на дату")

    tolerance = values.get("tolerance_minutes")
    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or not 0 <= tolerance <= 240:
        raise bad_request("Допустимая задержка: от 0 до 240 минут")

    on_date = parse_date(values.get("on_date"), required=False)
    if kind == TaskKind.ONE_TIME and on_date is None:
        raise bad_request("Для разовой задачи укажите дату")
    if kind == TaskKind.DAILY:
        on_date = None

    return {
        "title": clean_text(values.get("title"), "название задачи", 200),
        "kind": kind,
        "planned_time": parse_time(values.get("planned_time")),
        "on_date": on_date,
        "tolerance_minutes": tolerance,
        "requires_photo": clean_bool(values.get("requires_photo"), "нужно фото"),
        "requires_claim": clean_bool(values.get("requires_claim"), "принятие ответственности"),
    }


def current_values(template: TaskTemplate) -> dict:
    return {
        "title": template.title,
        "kind": template.kind,
        "planned_time": template.planned_time.strftime("%H:%M"),
        "on_date": template.on_date.isoformat() if template.on_date else None,
        "tolerance_minutes": template.tolerance_minutes,
        "requires_photo": template.requires_photo,
        "requires_claim": template.requires_claim,
    }


class TaskTemplateListView(APIView):
    def get(self, request, store_id):
        store = get_store(request, store_id)
        templates = store.task_templates.filter(is_active=True).order_by("planned_time", "id")
        return Response([template_item(template) for template in templates])

    def post(self, request, store_id):
        store = get_store(request, store_id)
        values = clean_template({**DEFAULTS, **request.data})
        template = TaskTemplate.objects.create(store=store, **values)
        return Response(template_item(template), status=status.HTTP_201_CREATED)


class TaskTemplateDetailView(APIView):
    def patch(self, request, template_id):
        template = get_template(request, template_id)
        values = clean_template({**current_values(template), **request.data})
        for field, value in values.items():
            setattr(template, field, value)
        template.save()
        return Response(template_item(template))

    def delete(self, request, template_id):
        template = get_template(request, template_id)
        # Deactivate instead of deleting: the history of completed tasks stays intact.
        template.is_active = False
        template.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
