from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings
from .presentation import reminder_offset_label


def draft_keyboard(
    post_id: int, selected: set[str], settings: Settings, event_enabled: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for target in settings.targets:
        mark = "✅" if target.key in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {target.name}", callback_data=f"target:{post_id}:{target.index}"
        )])
    event_mark = "✅" if event_enabled else "⬜"
    rows.extend([
        [InlineKeyboardButton(
            text=f"{event_mark} Регистрация на мероприятие",
            callback_data=f"event:{post_id}",
        )],
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"now:{post_id}")],
        [InlineKeyboardButton(text="🕒 Запланировать", callback_data=f"schedule:{post_id}")],
        [InlineKeyboardButton(text="✖ Отменить", callback_data=f"cancel:{post_id}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_cancel_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отменить публикацию", callback_data=f"cancel:{post_id}")
    ]])


def binary_registration_keyboard(post_id: int, field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Да", callback_data=f"registration_answer:{post_id}:{field}:1"
        ),
        InlineKeyboardButton(
            text="Нет", callback_data=f"registration_answer:{post_id}:{field}:0"
        ),
    ]])


def reminder_choice_keyboard(
    post_id: int, options_minutes: tuple[int, ...]
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=reminder_offset_label(minutes),
        callback_data=f"reminder:{post_id}:{minutes}",
    )] for minutes in options_minutes]
    rows.append([InlineKeyboardButton(
        text="Не напоминать", callback_data=f"reminder:{post_id}:0"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Записаться на мероприятие", callback_data="available_events"
        )],
        [InlineKeyboardButton(text="Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="Настройка профиля", callback_data="profile_settings")],
    ])


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Интерфейс пользователя", callback_data="show_user_interface"
        )
    ]])


def _navigation_row(prefix: str, page: int, pages: int) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton(text="←", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        row.append(InlineKeyboardButton(text="→", callback_data=f"{prefix}:{page + 1}"))
    return row


def available_events_keyboard(
    events: list[dict], page: int, pages: int
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"Зарегистрироваться · {index}",
        callback_data=f"register_event:{event['post_id']}",
    )] for index, event in enumerate(events, 1)]
    rows.append(_navigation_row("available_events_page", page, pages))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_events_keyboard(
    events: list[dict], page: int, pages: int
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"Отменить регистрацию · {index}",
        callback_data=f"unregister:{event['post_id']}:{page}",
    )] for index, event in enumerate(events, 1)]
    rows.append(_navigation_row("my_events_page", page, pages))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_events_page_keyboard(
    events: list[dict], page: int, pages: int, past: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, event in enumerate(events, 1):
        row = [InlineKeyboardButton(
            text=f"Участники · {index}",
            callback_data=f"participants:{event['post_id']}",
        )]
        if not past:
            row.append(InlineKeyboardButton(
                text="Отменить", callback_data=f"cancel_event:{event['post_id']}"
            ))
        rows.append(row)
    kind = "past" if past else "active"
    rows.append(_navigation_row(f"admin_events_page:{kind}", page, pages))
    rows.append([InlineKeyboardButton(
        text="Активные мероприятия" if past else "Прошедшие мероприятия",
        callback_data="admin_events_page:active:0" if past else "admin_events_page:past:0",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Изменить профиль", callback_data="edit_profile")
    ]])


def profile_answer_keyboard(field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"profile_answer:{field}:1"),
        InlineKeyboardButton(text="Нет", callback_data=f"profile_answer:{field}:0"),
    ]])


def registration_cancel_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отменить регистрацию", callback_data=f"unregister:{post_id}")
    ]])


def attendance_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да", callback_data=f"attendance:{post_id}:1"),
        InlineKeyboardButton(text="Нет", callback_data=f"attendance:{post_id}:0"),
    ]])


def confirm_event_cancellation_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Да, отменить мероприятие",
            callback_data=f"confirm_cancel_event:{post_id}",
        )],
        [InlineKeyboardButton(text="Нет", callback_data="dismiss_cancel_event")],
    ])
