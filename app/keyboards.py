from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings


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


def registration_link_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Зарегистрироваться", url=url)
    ]])


def reminder_choice_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, напомнить", callback_data=f"reminder:{post_id}:1")],
        [InlineKeyboardButton(text="Нет, без напоминания", callback_data=f"reminder:{post_id}:0")],
    ])


def user_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="Изменить имя", callback_data="edit_profile")],
    ])


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Изменить имя", callback_data="edit_profile")
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


def admin_event_keyboard(post_id: int, can_cancel: bool = True) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text="Участники", callback_data=f"participants:{post_id}"
    )]]
    if can_cancel:
        rows.append([InlineKeyboardButton(
            text="Отменить мероприятие", callback_data=f"cancel_event:{post_id}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def past_events_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Прошедшие мероприятия", callback_data="past_events"
        )
    ]])


def confirm_event_cancellation_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Да, отменить мероприятие",
            callback_data=f"confirm_cancel_event:{post_id}",
        )],
        [InlineKeyboardButton(text="Нет", callback_data="dismiss_cancel_event")],
    ])
