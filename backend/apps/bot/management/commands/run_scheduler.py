import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.bot.scheduler import tick

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the reminder / overdue / escalation scheduler loop"

    def handle(self, *args, **options):
        log.info("scheduler started, interval %ss", settings.SCHEDULER_INTERVAL_SECONDS)
        while True:
            try:
                tick(timezone.now())
            except Exception:
                log.exception("scheduler tick failed")
            close_old_connections()
            time.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
