from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Employee, EmployeeStatus, InviteCode, Store

from ..presenters import person, store_with_people
from ..scoping import (
    bad_request,
    clean_text,
    get_employee,
    get_store,
    owner_network,
    parse_time,
)


def clean_closed_weekdays(value) -> list[int]:
    """Дни недели, когда точка закрыта: 0 — понедельник, 6 — воскресенье."""
    if value is None:
        return []
    if not isinstance(value, list) or any(
        isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6 for day in value
    ):
        raise bad_request("Выходные — список дней недели от 0 (пн) до 6 (вс)")
    days = sorted(set(value))
    if len(days) == 7:
        raise bad_request("Точка не может быть закрыта всю неделю")
    return days


def clean_store(values: dict) -> dict:
    """Поля точки целиком: и для создания, и для правки поверх текущих значений."""
    open_time, close_time = parse_time(values.get("open_time")), parse_time(values.get("close_time"))
    if close_time <= open_time:
        raise bad_request("Магазин должен закрываться позже, чем открывается")
    return {
        "name": clean_text(values.get("name"), "название", 200),
        "address": clean_text(values.get("address"), "адрес", 300, required=False),
        "open_time": open_time,
        "close_time": close_time,
        "closed_weekdays": clean_closed_weekdays(values.get("closed_weekdays")),
    }


class StoreListView(APIView):
    def get(self, request):
        stores = (
            owner_network(request)
            .stores.filter(is_active=True)
            .order_by("name")
            .prefetch_related("employees__invites")
        )
        return Response([store_with_people(store) for store in stores])

    def post(self, request):
        network = owner_network(request)
        store = Store.objects.create(network=network, **clean_store(request.data))
        return Response(store_with_people(store), status=status.HTTP_201_CREATED)


class StoreDetailView(APIView):
    def get(self, request, store_id):
        return Response(store_with_people(get_store(request, store_id)))

    def patch(self, request, store_id):
        """
        Правка точки после создания: название, адрес, часы работы, выходные.

        Приходят только изменённые поля, поэтому проверяем их вместе с текущими:
        новое закрытие должно быть позже старого открытия, и наоборот.
        """
        store = get_store(request, store_id)
        current = {
            "name": store.name,
            "address": store.address,
            "open_time": store.open_time.strftime("%H:%M"),
            "close_time": store.close_time.strftime("%H:%M"),
            "closed_weekdays": store.closed_weekdays,
        }
        values = clean_store({**current, **request.data})
        for field, value in values.items():
            setattr(store, field, value)
        store.save(update_fields=list(values))
        return Response(store_with_people(store))


class StoreEmployeesView(APIView):
    def post(self, request, store_id):
        store = get_store(request, store_id)
        with transaction.atomic():
            employee = Employee.objects.create(
                store=store, name=clean_text(request.data.get("name"), "имя сотрудника", 150)
            )
            InviteCode.issue(employee)
        return Response(person(employee), status=status.HTTP_201_CREATED)


class EmployeeInviteView(APIView):
    def post(self, request, employee_id):
        employee = get_employee(request, employee_id)
        if employee.status == EmployeeStatus.DISMISSED:
            return Response({"detail": "Сотрудник уволен"}, status=status.HTTP_409_CONFLICT)
        if employee.account_id:
            return Response({"detail": "Сотрудник уже подключён к боту"}, status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            employee.invites.filter(used_at__isnull=True).delete()
            InviteCode.issue(employee)
        return Response(person(employee))


class EmployeeDeleteView(APIView):
    def delete(self, request, employee_id):
        """
        Убрать уволенного сотрудника из списка.

        Если он ни разу не работал — запись удаляем целиком. Если за ним есть смены или
        отметки, запись остаётся: на неё ссылается история задач, и «Отметил Пётр С.»
        не должно превратиться в пустое место. Из списка сотрудников он пропадает.
        """
        employee = get_employee(request, employee_id)
        if employee.status == EmployeeStatus.ACTIVE:
            return Response(
                {"detail": "Сначала отметьте, что сотрудник уволен"},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            employee.invites.all().delete()
            never_worked = not (
                employee.shifts.exists()
                or employee.completions.exists()
                or employee.claims.exists()
            )
            if never_worked:
                employee.delete()
            else:
                employee.status = EmployeeStatus.REMOVED
                employee.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeDismissView(APIView):
    def post(self, request, employee_id):
        employee = get_employee(request, employee_id)
        with transaction.atomic():
            employee.status = EmployeeStatus.DISMISSED
            employee.save(update_fields=["status"])
            employee.invites.filter(used_at__isnull=True).delete()
        # History stays: completions keep pointing at the employee, only the status changes.
        return Response(person(employee))
