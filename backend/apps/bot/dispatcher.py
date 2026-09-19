import logging

from . import keyboards, texts
from .handlers import onboarding, tasks

log = logging.getLogger(__name__)


def dispatch(client, update: dict) -> None:
    update_type = update.get("update_type")
    if update_type == "bot_started":
        onboarding.on_bot_started(client, update)
    elif update_type == "message_created":
        onboarding.on_message_created(client, update)
    elif update_type == "message_callback":
        dispatch_callback(client, update)
    else:
        log.debug("ignored update type %s", update_type)


def dispatch_callback(client, update: dict) -> None:
    callback = update["callback"]
    action, arg = keyboards.parse_callback(callback.get("payload", ""))
    account = onboarding.upsert_account(
        callback["user"], ((update.get("message") or {}).get("recipient") or {}).get("chat_id")
    )
    if action == "role":
        onboarding.on_role_chosen(client, account, callback["callback_id"], arg)
    elif action == "done" and arg.isdigit():
        tasks.on_done(client, account, callback["callback_id"], int(arg))
    elif action == "claim" and arg.isdigit():
        tasks.on_claim(client, account, callback["callback_id"], int(arg))
    else:
        client.answer_callback(callback["callback_id"], text=texts.UNKNOWN)
