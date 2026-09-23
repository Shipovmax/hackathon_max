from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.domain.day import day_tasks, published_shifts
from apps.core.domain.lifecycle import store_zone
from apps.core.models import TaskStatus

from ..presenters import day_task
from ..scoping import get_store, hhmm, owner_network, parse_date

DONE = {TaskStatus.DONE_ON_TIME, TaskStatus.DONE_LATE}
# Красный: задача не сделана. Жёлтый: сделана, но позже срока — владельца уже уведомили,
# вмешиваться не нужно, но точке стоит присмотреться.
NOT_DONE = {TaskStatus.OVERDUE, TaskStatus.MISSED}
# Сначала то, что горит, потом опоздания, потом всё в порядке.
HEALTH_ORDER = {"unclaimed": 0, "overdue": 0, "late": 1, "ok": 2}


class DashboardView(APIView):
    def get(self, request):
        network = owner_network(request)
        now = timezone.now()
        day = parse_date(request.query_params.get("date"), required=False) or timezone.localdate(now)

        stores = []
        for store in network.stores.filter(is_active=True).order_by("name"):
            rows = day_tasks(store, day, now)
            statuses = {row.status for row in rows}
            completions = [
                row.instance.completion
                for row in rows
                if row.instance is not None and hasattr(row.instance, "completion")
            ]
            last = max(completions, key=lambda item: item.completed_at, default=None)

            if TaskStatus.UNCLAIMED in statuses:
                health = "unclaimed"
            elif statuses & NOT_DONE:
                health = "overdue"
            elif TaskStatus.DONE_LATE in statuses:
                health = "late"
            else:
                health = "ok"

            stores.append(
                {
                    "id": store.id,
                    "name": store.name,
                    "done": sum(1 for row in rows if row.status in DONE),
                    "total": len(rows),
                    "health": health,
                    "last_event_label": (
                        f"последнее {hhmm(last.completed_at.astimezone(store_zone(store)))}" if last else None
                    ),
                }
            )

        # Stores with problems come first, so the owner does not have to hunt for them.
        stores.sort(key=lambda item: HEALTH_ORDER[item["health"]])
        return Response({"date": day.isoformat(), "stores": stores})


class StoreDayView(APIView):
    def get(self, request, store_id):
        store = get_store(request, store_id)
        now = timezone.now()
        day = parse_date(request.query_params.get("date"), required=False) or timezone.localdate(now)
        zone = store_zone(store)

        return Response(
            {
                "store": {"id": store.id, "name": store.name},
                "date": day.isoformat(),
                "closed": store.is_closed_on(day),
                "on_shift": [
                    {"name": shift.employee.name, "start": hhmm(shift.start_time), "end": hhmm(shift.end_time)}
                    for shift in published_shifts(store, day)
                ],
                "tasks": [day_task(row, zone) for row in day_tasks(store, day, now)],
            }
        )
