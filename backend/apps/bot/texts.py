from django.conf import settings


def plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def minutes(n: int) -> str:
    return f"{n} {plural_ru(n, ('минуту', 'минуты', 'минут'))}"


def tasks_word(n: int) -> str:
    return plural_ru(n, ("задачи", "задач", "задач"))


PRIVACY_URL = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/privacy/" if settings.PUBLIC_BASE_URL else ""


def with_privacy(text: str, lead: str, url: str = PRIVACY_URL) -> str:
    return f"{text}\n\n{lead}: {url}" if url else text


ROLE_PROMPT = with_privacy(
    "Кто вы: владелец сети или сотрудник магазина?",
    "Продолжая, вы соглашаетесь с политикой обработки персональных данных",
)
DEFAULT_NETWORK_NAME = "Моя сеть"
ROLE_OWNER_CHOSEN = "Вы владелец. Настройки и сводка по точкам — в приложении."
OPEN_APP_PROMPT = "Откройте приложение, чтобы добавить точки, сотрудников и график."
ROLE_EMPLOYEE_ASK_CODE = with_privacy(
    "Отправьте код, который вам дал владелец.",
    "Отправляя код, вы соглашаетесь с политикой обработки персональных данных",
)
CODE_INVALID = "Код не найден или уже использован. Попросите у владельца новый."
WELCOME_BACK_OWNER = "Вы владелец. Сводка по точкам — в приложении."
WELCOME_BACK_EMPLOYEE = "Вы подключены. Напишите «что осталось», чтобы увидеть задачи на смену."
UNKNOWN = "Не понял. Для смены роли отправьте /role."
PHOTO_FAILED = "Не получилось загрузить фото. Задача осталась открытой — попробуйте ещё раз."
PHOTO_NOT_EXPECTED = "Сейчас нет задачи, ожидающей фото. Напишите «что осталось»."
CLAIM_REQUIRED = "Сначала возьмите задачу кнопкой «Беру»."
CLAIM_NOT_AVAILABLE = (
    "Эта задача не относится к вашей смене. "
    "Её возьмёт сотрудник, который работает в это время."
)
NOT_IMPLEMENTED = "Эта часть бота ещё в разработке."

BOARD_SHIFT_STARTED = "Смена началась"
BOARD_STATUS = "Задачи смены"
BOARD_UPDATED = "Список задач изменился"
BOARD_HINT = "Отметьте задачу кнопкой под сообщением."


def code_accepted(store_name: str) -> str:
    return (
        f"Готово. Вы подключены к точке {store_name}.\n\n"
        "Владелец точки видит ваше имя, время отметок задач и присланные фото. "
        "Эти данные нужны только для контроля задач смены."
    )


def shift_board(
    heading: str,
    store_name: str,
    shift_start: str,
    shift_end: str,
    rows: list[tuple[str, str, str, str]],
    done: int,
    total: int,
) -> str:
    head = [heading, f"{store_name} · смена {shift_start}–{shift_end}"]
    if total == 0:
        head.append("Задач на эту смену нет")
        return "\n".join(head)

    head.append(f"Выполнено {done} из {total} {tasks_word(total)}")
    lines = [f"{mark} {at} {title}" + (f" — {note}" if note else "") for mark, at, title, note in rows]
    tail = [BOARD_HINT] if done < total else []
    return "\n".join(head) + "\n\n" + "\n".join(lines) + ("\n\n" + "\n".join(tail) if tail else "")


def board_row_open(deadline: str, needs_photo: bool) -> str:
    return f"отметить до {deadline}" + (", нужно фото" if needs_photo else "")


def board_row_done(employee_name: str, at: str, late_minutes: int) -> str:
    if late_minutes:
        return f"{employee_name} в {at}, с опозданием на {minutes(late_minutes)}"
    return f"{employee_name} в {at}, вовремя"


def board_row_awaiting(employee_name: str) -> str:
    return f"ждём фото от {employee_name}"


def board_row_overdue(deadline: str) -> str:
    return f"просрочено с {deadline}, владелец уведомлён"


def board_row_unclaimed(planned: str) -> str:
    return f"с {planned} никто не взял"


BOARD_ROW_MISSED = "не выполнено за смену"


def board_row_not_yet(available_from: str) -> str:
    return f"отметить можно с {available_from}"


def board_row_claim_free(planned: str) -> str:
    return f"в {planned}, нужно нажать «Беру»"


def done_heading(task_title: str, at: str, late_minutes: int) -> str:
    if late_minutes:
        return f"Готово: «{task_title}» отмечено в {at}, с опозданием на {minutes(late_minutes)}"
    return f"Готово: «{task_title}» отмечено в {at}, вовремя"


def photo_accepted_heading(task_title: str, at: str, late_minutes: int) -> str:
    base = f"Фото принято, «{task_title}» отмечено в {at}"
    return base + (f", с опозданием на {minutes(late_minutes)}" if late_minutes else ", вовремя")


def done_by_other_heading(task_title: str, employee_name: str, at: str) -> str:
    return f"«{task_title}» отмечено: {employee_name}, {at}"


def claimed_heading(task_title: str, planned: str) -> str:
    return f"Задача «{task_title}» в {planned} теперь за вами"


def ask_photo_for(
    task_title: str,
    planned: str,
    deadline: str,
    wait_minutes: int,
    prompt: str = "",
) -> str:
    what = prompt or "Пришлите фото, которое подтверждает выполнение."
    return (
        f"Задача «{task_title}», плановое время {planned}.\n\n"
        f"{what}\n"
        f"Снимайте зал, товар или документы — без покупателей и посторонних людей в кадре.\n"
        f"Одним сообщением в этот чат. Отметка встанет на момент получения фото, "
        f"задача принимается до {deadline}.\n"
        f"Если фото не придёт за {minutes(wait_minutes)}, задача снова станет открытой "
        f"и её сможет отметить любой сотрудник смены."
    )


def reminder(task_title: str, planned: str, deadline: str, minutes_left: int, final: bool) -> str:
    head = "Последнее напоминание" if final else "Напоминание"
    return (
        f"{head}: «{task_title}», плановое время {planned}.\n"
        f"Осталось {minutes(minutes_left)}: после {deadline} задача станет просроченной "
        f"и о ней узнает владелец."
    )


def planned_time_reminder(
    task_title: str, planned: str, minutes_left: int, final: bool
) -> str:
    head = "Последнее напоминание до планового времени" if final else "Напоминание"
    return (
        f"{head}: «{task_title}», плановое время {planned}.\n"
        f"Осталось {minutes(minutes_left)} до планового времени."
    )


def awaiting_photo_by(task_title: str, employee_name: str) -> str:
    return f"Задача «{task_title}» уже ожидает фото от {employee_name}."


def finish_pending_photo(task_title: str) -> str:
    return f"Сначала пришлите фото для задачи «{task_title}»."


def claim_question(at: str, task_title: str) -> str:
    return f"Сегодня в {at} {task_title.lower()}. Кто принимает?"


def claim_taken_by(task_title: str, at: str, employee_name: str) -> str:
    return f"{task_title} в {at} выполняет {employee_name}."


def claim_escalation(task_title: str, at: str, minutes_left: int) -> str:
    return f"{task_title} в {at} ещё никто не взял. Осталось {minutes(minutes_left)}."


def shift_summary(done: int, total: int, not_marked: list[str]) -> str:
    text = f"Смена завершена. Выполнено {done} из {total}"
    return f"{text}\nНе отмечено: {', '.join(not_marked)}" if not_marked else text


def status_not_started(shift_start: str) -> str:
    return f"Ваша смена сегодня с {shift_start}. Задачи появятся после начала смены."


def status_ended(shift_end: str) -> str:
    return f"Ваша смена завершилась в {shift_end}. Итог придёт отдельным сообщением."


def denial_day_off(next_shift: str | None) -> str:
    if next_shift:
        return f"Сегодня у вас выходной. Ближайшая смена — {next_shift}"
    return "Сегодня у вас выходной. Ближайшая смена ещё не опубликована."


def denial_not_started(shift_start: str, task_title: str, who_starts: str) -> str:
    return f"Ваша смена сегодня с {shift_start}. Отметить {task_title.lower()} может тот, кто работает с {who_starts}."


def denial_ended(shift_end: str, task_title: str, who_ends: str) -> str:
    return f"Ваша смена завершилась в {shift_end}. {task_title} отметит {who_ends}."


def denial_too_early(task_title: str, available_from: str, planned: str) -> str:
    return (
        f"{task_title} можно отметить с {available_from}, плановое время — {planned}. "
        f"Задача появится в списке, когда подойдёт срок."
    )


def denial_already_done(task_title: str, employee_name: str, at: str) -> str:
    return f"{task_title} уже отмечено: {employee_name}, {at}."


def owner_overdue(store_name: str, task_title: str, planned_at: str) -> str:
    return f"{store_name}: задача «{task_title}» не отмечена. Плановое время — {planned_at}."


def owner_closed_late(store_name: str, task_title: str, at: str, late: int, employee_name: str) -> str:
    return (
        f"{store_name}: задача «{task_title}» выполнена в {at}, "
        f"с опозданием на {minutes(late)}. Кто отметил: {employee_name}"
    )


def owner_unclaimed(store_name: str, task_title: str, at: str) -> str:
    return f"{store_name}: задачу «{task_title}» в {at} никто не взял."
