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
        body = request.data
        open_time, close_time = parse_time(body.get("open_time")), parse_time(body.get("close_time"))
        if close_time <= open_time:
            raise bad_request("Магазин должен закрываться позже, чем открывается")
        store = Store.objects.create(
            network=network,
            name=clean_text(body.get("name"), "название", 200),
            address=clean_text(body.get("address"), "адрес", 300, required=False),
            open_time=open_time,
            close_time=close_time,
        )
        return Response(store_with_people(store), status=status.HTTP_201_CREATED)


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
