"""Ownership checks and input parsing shared by the API views. Errors carry a `detail` the mini-app shows as is."""

from datetime import date, datetime, time

from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import Employee, Network, Store, TaskTemplate


def bad_request(message: str) -> ValidationError:
    return ValidationError({"detail": message})


def not_found(message: str) -> NotFound:
    return NotFound({"detail": message})


def owner_network(request) -> Network:
    network = getattr(request.user, "network", None)
    if network is None:
        raise not_found("Сеть не найдена")
    return network


def get_store(request, store_id: int) -> Store:
    try:
        return Store.objects.get(pk=store_id, network=owner_network(request), is_active=True)
    except Store.DoesNotExist:
        raise not_found("Точка не найдена")


def get_employee(request, employee_id: int) -> Employee:
    try:
        return Employee.objects.select_related("store").get(
            pk=employee_id, store__network=owner_network(request)
        )
    except Employee.DoesNotExist:
        raise not_found("Сотрудник не найден")


def get_template(request, template_id: int) -> TaskTemplate:
    try:
        return TaskTemplate.objects.select_related("store").get(
            pk=template_id, store__network=owner_network(request), is_active=True
        )
    except TaskTemplate.DoesNotExist:
        raise not_found("Задача не найдена")


def request_body(request) -> dict:
    """Тело запроса — JSON-объект. Массив, число или null — ошибка ввода, а не 500."""
    body = request.data
    if not isinstance(body, dict):
        raise bad_request("Тело запроса должно быть JSON-объектом")
    return body


# Дальше этих лет дат в работе магазина не бывает, а у края календаря ломается
# арифметика недель (понедельник 0001-01-01, неделя после 9999-12-31).
MIN_YEAR, MAX_YEAR = 2000, 2100


def parse_date(value, *, required: bool = True) -> date | None:
    if value in (None, ""):
        if required:
            raise bad_request("Не указана дата")
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        raise bad_request("Дата указана неверно")
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise bad_request("Дата указана неверно")
    return parsed


def parse_time(value) -> time:
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except ValueError:
        raise bad_request("Время указано неверно, ожидается ЧЧ:ММ")


def hhmm(value: time | datetime) -> str:
    return value.strftime("%H:%M")


def clean_text(value, label: str, max_length: int, *, required: bool = True) -> str:
    if value is not None and not isinstance(value, str):
        raise bad_request(f"Поле «{label}» должно быть текстом")
    # PostgreSQL не хранит нулевой символ в тексте и ответил бы ошибкой сервера.
    if value and "\x00" in value:
        raise bad_request(f"Поле «{label}» содержит недопустимый символ")
    text = (value or "").strip()
    if required and not text:
        raise bad_request(f"Укажите {label}")
    if len(text) > max_length:
        raise bad_request(f"{label.capitalize()} слишком длинное")
    return text


def clean_bool(value, label: str) -> bool:
    if not isinstance(value, bool):
        raise bad_request(f"Поле «{label}» должно быть да или нет")
    return value
