import logging
import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.bot.dispatcher import dispatch
from apps.bot.max_api.client import MaxApiError, MaxClient

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Receive MAX updates via Long Polling and dispatch them to the bot handlers"

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError("BOT_TOKEN is not set")
        client = MaxClient()
        log.info("polling as @%s", client.get_me().get("username"))

        marker = None
        backoff = 1
        while True:
            try:
                data = client.get_updates(marker=marker)
            except MaxApiError as error:
                if error.status_code == 401:
                    raise CommandError("MAX API rejected BOT_TOKEN (401)")
                log.warning("get_updates failed: %s", error)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            except httpx.HTTPError as error:
                log.warning("get_updates network error: %r", error)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue

            backoff = 1
            marker = data.get("marker", marker)
            for update in data.get("updates", []):
                try:
                    dispatch(client, update)
                except Exception:
                    log.exception("failed to handle %s", update.get("update_type"))
            close_old_connections()
