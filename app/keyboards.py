from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings


def draft_keyboard(post_id: int, selected: set[str], settings: Settings) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for target in settings.targets:
        mark = "✅" if target.key in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {target.name}", callback_data=f"target:{post_id}:{target.index}"
        )])
    rows.extend([
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"now:{post_id}")],
        [InlineKeyboardButton(text="🕒 Запланировать", callback_data=f"schedule:{post_id}")],
        [InlineKeyboardButton(text="✖ Отменить", callback_data=f"cancel:{post_id}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_cancel_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отменить публикацию", callback_data=f"cancel:{post_id}")
    ]])
