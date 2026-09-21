"""User-facing bot messages. Tone: short, no exclamation marks, a refusal always says who does it instead (CLAUDE.md §14)."""


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


ROLE_PROMPT = "Кто вы: владелец сети или сотрудник магазина?"
DEFAULT_NETWORK_NAME = "Моя сеть"
ROLE_OWNER_CHOSEN = "Вы владелец. Настройки и сводка по точкам — в приложении."
OPEN_APP_PROMPT = "Откройте приложение, чтобы добавить точки, сотрудников и график."
ROLE_EMPLOYEE_ASK_CODE = "Отправьте код, который вам дал владелец."
CODE_INVALID = "Код не найден или уже использован. Попросите у владельца новый."
WELCOME_BACK_OWNER = "Вы владелец. Сводка по точкам — в приложении."
WELCOME_BACK_EMPLOYEE = "Вы подключены. Напишите «что осталось», чтобы увидеть задачи на смену."
UNKNOWN = "Не понял. Для смены роли отправьте /role."
PHOTO_FAILED = "Не получилось загрузить фото. Задача осталась открытой — попробуйте ещё раз."
PHOTO_NOT_EXPECTED = "Сейчас нет задачи, ожидающей фото. Напишите «что осталось»."
NOT_IMPLEMENTED = "Эта часть бота ещё в разработке."


def code_accepted(store_name: str) -> str:
    return f"Готово. Вы подключены к точке {store_name}."


def shift_started(store_name: str, until: str, tasks: list[tuple[str, str]]) -> str:
    lines = "\n".join(f"{at} {title}" for at, title in tasks)
    heading = f"Смена началась. {store_name} · до {until}"
    return f"{heading}\n\n{lines}" if lines else heading


def reminder(minutes_left: int, task_title: str) -> str:
    return f"Через {minutes(minutes_left)} — {task_title.lower()}"


def ask_photo(prompt: str = "") -> str:
    return prompt or "Пришлите фото"


def marked(task_title: str, at: str, next_at: str | None = None) -> str:
    text = f"{task_title} отмечено в {at}"
    return f"{text}. Следующая задача — в {next_at}" if next_at else text


def awaiting_photo_by(task_title: str, employee_name: str) -> str:
    return f"Задача «{task_title}» уже ожидает фото от {employee_name}."


def finish_pending_photo(task_title: str) -> str:
    return f"Сначала пришлите фото для задачи «{task_title}»."


def claim_question(at: str, task_title: str) -> str:
    return f"Сегодня в {at} {task_title.lower()}. Кто принимает?"


def claim_confirmed() -> str:
    return "Задача за вами. Отметьте, когда выполните."


def claim_taken_by(task_title: str, at: str, employee_name: str) -> str:
    return f"{task_title} в {at} выполняет {employee_name}."


def claim_escalation(task_title: str, at: str, minutes_left: int) -> str:
    return f"{task_title} в {at} ещё никто не взял. Осталось {minutes(minutes_left)}."


def shift_summary(done: int, total: int, not_marked: list[str]) -> str:
    text = f"Смена завершена. Выполнено {done} из {total}"
    return f"{text}\nНе отмечено: {', '.join(not_marked)}" if not_marked else text


def denial_day_off(next_shift: str | None) -> str:
    if next_shift:
        return f"Сегодня у вас выходной. Ближайшая смена — {next_shift}"
    return "Сегодня у вас выходной. Ближайшая смена ещё не опубликована."


def denial_not_started(shift_start: str, task_title: str, who_starts: str) -> str:
    return f"Ваша смена сегодня с {shift_start}. Отметить {task_title.lower()} может тот, кто работает с {who_starts}."


def denial_ended(shift_end: str, task_title: str, who_ends: str) -> str:
    return f"Ваша смена завершилась в {shift_end}. {task_title} отметит {who_ends}."


def denial_already_done(task_title: str, employee_name: str, at: str) -> str:
    return f"{task_title} отметил {employee_name} в {at}."


def owner_overdue(store_name: str, task_title: str, planned_at: str) -> str:
    return f"{store_name}: задача «{task_title}» не отмечена. Плановое время — {planned_at}."


def owner_closed_late(store_name: str, task_title: str, at: str, late: int, employee_name: str) -> str:
    return (
        f"{store_name}: задача «{task_title}» выполнена в {at}, "
        f"с опозданием на {minutes(late)}. Отметил: {employee_name}"
    )


def owner_unclaimed(store_name: str, task_title: str, at: str) -> str:
    return f"{store_name}: задачу «{task_title}» в {at} никто не взял."
