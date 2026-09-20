import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import Employee, EmployeeStatus, InviteCode, MaxAccount, Network, Role

from .. import keyboards, texts
from . import tasks

log = logging.getLogger(__name__)


def upsert_account(user: dict, chat_id: int | None) -> MaxAccount:
    account, _ = MaxAccount.objects.get_or_create(
        max_user_id=user["user_id"], defaults={"first_name": user.get("first_name") or ""}
    )
    changed = []
    if chat_id and account.dialog_chat_id != chat_id:
        account.dialog_chat_id = chat_id
        changed.append("dialog_chat_id")
    if user.get("first_name") and account.first_name != user["first_name"]:
        account.first_name = user["first_name"]
        changed.append("first_name")
    if changed:
        account.save(update_fields=changed)
    return account


def bound_employee(account: MaxAccount) -> Employee | None:
    return Employee.objects.filter(account=account, status=EmployeeStatus.ACTIVE).first()


def bind_by_code(account: MaxAccount, raw_code: str) -> Employee | None:
    code = "".join(raw_code.split()).upper()
    try:
        with transaction.atomic():
            invite = (
                InviteCode.objects.select_for_update()
                .select_related("employee__store")
                .filter(code=code, used_at__isnull=True, employee__status=EmployeeStatus.ACTIVE)
                .first()
            )
            if invite is None:
                return None
            employee = invite.employee
            employee.account = account
            employee.save(update_fields=["account"])
            invite.used_at = timezone.now()
            invite.save(update_fields=["used_at"])
            return employee
    except IntegrityError:
        log.warning("account %s is already bound to another employee", account.max_user_id)
        return None


def ask_role(client, account: MaxAccount) -> None:
    client.send_message(
        user_id=account.max_user_id, text=texts.ROLE_PROMPT, buttons=keyboards.role_choice()
    )


def on_bot_started(client, update: dict) -> None:
    account = upsert_account(update["user"], update.get("chat_id"))
    if not account.role:
        return ask_role(client, account)
    if account.role == Role.OWNER:
        client.send_message(
            user_id=account.max_user_id,
            text=texts.WELCOME_BACK_OWNER,
            buttons=keyboards.open_app(),
        )
    elif bound_employee(account):
        client.send_message(user_id=account.max_user_id, text=texts.WELCOME_BACK_EMPLOYEE)
    else:
        client.send_message(user_id=account.max_user_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)


def on_role_chosen(client, account: MaxAccount, callback_id: str, role: str) -> None:
    if role not in Role.values:
        client.answer_callback(callback_id, text=texts.UNKNOWN)
        return
    account.role = role
    account.save(update_fields=["role"])
    if role == Role.OWNER:
        Network.objects.get_or_create(owner=account, defaults={"name": texts.DEFAULT_NETWORK_NAME})
        client.answer_callback(callback_id, text=texts.ROLE_OWNER_CHOSEN)
        client.send_message(
            user_id=account.max_user_id, text=texts.OPEN_APP_PROMPT, buttons=keyboards.open_app()
        )
    elif bound_employee(account):
        client.answer_callback(callback_id, text=texts.WELCOME_BACK_EMPLOYEE)
    else:
        client.answer_callback(callback_id, text=texts.ROLE_EMPLOYEE_ASK_CODE)


def on_message_created(client, update: dict) -> None:
    message = update["message"]
    sender = message.get("sender") or {}
    if sender.get("is_bot") or "user_id" not in sender:
        return
    account = upsert_account(sender, (message.get("recipient") or {}).get("chat_id"))
    body = message.get("body") or {}
    text = (body.get("text") or "").strip()
    attachments = body.get("attachments") or []

    if text in ("/start", "/role"):
        return ask_role(client, account)
    if account.role == Role.EMPLOYEE:
        if any(item.get("type") == "image" for item in attachments):
            return tasks.on_photo(client, account, message)
        if bound_employee(account) is None:
            return reply_to_code(client, account, text)
        if text.lower() in ("что осталось", "/status"):
            return tasks.on_status(client, account)
    client.send_message(user_id=account.max_user_id, text=texts.UNKNOWN)


def reply_to_code(client, account: MaxAccount, text: str) -> None:
    employee = bind_by_code(account, text)
    if employee is None:
        client.send_message(user_id=account.max_user_id, text=texts.CODE_INVALID)
    else:
        client.send_message(
            user_id=account.max_user_id, text=texts.code_accepted(employee.store.name)
        )
