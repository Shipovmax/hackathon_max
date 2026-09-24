from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import EmployeeStatus, Shift, ShiftStatus

from ..presenters import gaps_of, monday_of, schedule_payload, week_dates, week_status
from ..scoping import bad_request, get_store, parse_date, parse_time, request_body


def parse_draft(request, store):
    """Validate {week_start, shifts} from the body: returns the week's Monday and parsed shift tuples."""
    body = request_body(request)
    week_start = monday_of(parse_date(body.get("week_start")))
    items = body.get("shifts")
    if not isinstance(items, list):
        raise bad_request("Не передан список смен")

    people = {employee.id: employee for employee in store.employees.all()}
    dates = set(week_dates(week_start))
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            raise bad_request("Смена указана неверно")
        employee_id = item.get("employee_id")
        if isinstance(employee_id, bool) or not isinstance(employee_id, int):
            raise bad_request("Сотрудник не найден на этой точке")
        employee = people.get(employee_id)
        if employee is None:
            raise bad_request("Сотрудник не найден на этой точке")
        # Смены уволенных график не правит: прошлые остаются историей, а приложение,
        # открытое до увольнения, могло прислать их вместе с остальными.
        if employee.status != EmployeeStatus.ACTIVE:
            continue
        day = parse_date(item.get("date"))
        if day not in dates:
            raise bad_request("Смена выходит за пределы выбранной недели")
        start, end = parse_time(item.get("start")), parse_time(item.get("end"))
        if end <= start:
            raise bad_request(f"У {employee.name} конец смены должен быть позже начала")
        parsed.append((employee, day, start, end))

    parsed.sort(key=lambda entry: (entry[0].id, entry[1], entry[2]))
    for previous, current in zip(parsed, parsed[1:]):
        if previous[0].id == current[0].id and previous[1] == current[1] and current[2] < previous[3]:
            raise bad_request(f"У {current[0].name} пересекаются смены {current[1].strftime('%d.%m')}")
    return week_start, parsed


def save_week(store, week_start, parsed, *, publish: bool) -> None:
    """Replace the week's shifts. A week that is already published stays published, so edits go live at once."""
    keep_published = publish or week_status(store, week_start) == "published"
    status = ShiftStatus.PUBLISHED if keep_published else ShiftStatus.DRAFT
    with transaction.atomic():
        # Заменяем смены только работающих: смены уволенных — история, её не трогаем.
        Shift.objects.filter(
            store=store, date__in=week_dates(week_start), employee__status=EmployeeStatus.ACTIVE
        ).delete()
        Shift.objects.bulk_create(
            Shift(
                employee=employee, store=store, date=day, start_time=start, end_time=end, status=status
            )
            for employee, day, start, end in parsed
        )


class ScheduleView(APIView):
    def get(self, request, store_id):
        store = get_store(request, store_id)
        requested = parse_date(request.query_params.get("week"), required=False)
        week_start = monday_of(requested or timezone.localdate())
        return Response(schedule_payload(store, week_start))

    def put(self, request, store_id):
        store = get_store(request, store_id)
        week_start, parsed = parse_draft(request, store)
        save_week(store, week_start, parsed, publish=False)
        return Response(schedule_payload(store, week_start))


class CoverageView(APIView):
    def post(self, request, store_id):
        store = get_store(request, store_id)
        week_start, parsed = parse_draft(request, store)
        gaps = gaps_of(store, week_dates(week_start), [(day, start, end) for _, day, start, end in parsed])
        return Response({"gaps": gaps})


class PublishView(APIView):
    def post(self, request, store_id):
        store = get_store(request, store_id)
        week_start, parsed = parse_draft(request, store)
        if not parsed:
            raise bad_request("Добавьте хотя бы одну смену, чтобы опубликовать график")
        save_week(store, week_start, parsed, publish=True)
        return Response(schedule_payload(store, week_start))
