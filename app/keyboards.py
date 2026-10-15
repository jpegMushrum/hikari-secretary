from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings
from .presentation import event_title, reminder_offset_label


def draft_keyboard(
    post_id: int,
    selected: set[str],
    settings: Settings,
    event_enabled: bool = False,
    event_limit_reached: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for target in settings.targets:
        mark = "✅" if target.key in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {target.name}", callback_data=f"target:{post_id}:{target.index}"
        )])
    event_mark = "✅" if event_enabled else "⬜"
    event_text = (
        "Превышен лимит"
        if event_limit_reached and not event_enabled
        else f"{event_mark} Регистрация на мероприятие"
    )
    rows.extend([
        [InlineKeyboardButton(
            text=event_text,
            callback_data=f"event:{post_id}",
        )],
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"now:{post_id}")],
        [InlineKeyboardButton(text="🕒 Запланировать", callback_data=f"schedule:{post_id}")],
        [InlineKeyboardButton(text="✖ Отменить", callback_data=f"cancel:{post_id}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_cancel_keyboard(post_id: int, ai_generated: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ai_generated:
        rows.extend([
            [InlineKeyboardButton(
                text="👁 Предпросмотр", callback_data=f"ai_queue_preview:{post_id}"
            )],
            [
                InlineKeyboardButton(
                    text="✏️ Исправить", callback_data=f"ai_queue_revise:{post_id}"
                ),
                InlineKeyboardButton(
                    text="🔄 Перегенерировать",
                    callback_data=f"ai_queue_regenerate:{post_id}",
                ),
            ],
        ])
    rows.append([InlineKeyboardButton(
        text="Отменить публикацию", callback_data=f"cancel:{post_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def binary_registration_keyboard(post_id: int, field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Да", callback_data=f"registration_answer:{post_id}:{field}:1"
        ),
        InlineKeyboardButton(
            text="❌ Нет", callback_data=f"registration_answer:{post_id}:{field}:0"
        ),
    ]])


def reminder_choice_keyboard(
    post_id: int, options_minutes: tuple[int, ...]
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"🔔 {reminder_offset_label(minutes)}",
        callback_data=f"reminder:{post_id}:{minutes}",
    )] for minutes in options_minutes]
    rows.append([InlineKeyboardButton(
        text="🔕 Не напоминать", callback_data=f"reminder:{post_id}:0"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_menu_keyboard(show_admin_return: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text="🎟 Найти мероприятие", callback_data="available_events"
        )],
        [InlineKeyboardButton(text="📅 Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_settings")],
    ]
    if show_admin_return:
        rows.append([InlineKeyboardButton(
            text="⚙️ Панель администратора", callback_data="admin_home"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Мероприятия и публикации", callback_data="admin_events_menu"
        )],
        [InlineKeyboardButton(text="🤖 ИИ", callback_data="admin_ai_menu")],
        [InlineKeyboardButton(text="💬 Отзывы", callback_data="admin_feedback")],
        [InlineKeyboardButton(
            text="👤 Интерфейс пользователя", callback_data="show_user_interface"
        )],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="admin_help")],
    ])


def admin_events_menu_keyboard(
    publication_limit_reached: bool = False,
) -> InlineKeyboardMarkup:
    publication_text = (
        "Превышен лимит"
        if publication_limit_reached
        else "✍️ Создать публикацию"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=publication_text, callback_data="admin_new_post"
        )],
        [
            InlineKeyboardButton(text="🕒 Очередь", callback_data="admin_queue"),
            InlineKeyboardButton(
                text="👥 Мероприятия", callback_data="admin_registrations"
            ),
        ],
        [InlineKeyboardButton(text="← Панель администратора", callback_data="admin_home")],
    ])


def admin_ai_menu_keyboard(
    configured: bool,
    selected_level: str = "N3",
    has_comment: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if configured:
        rows.append([InlineKeyboardButton(
            text="✨ Сгенерировать тему", callback_data="ai_generate"
        )])
        rows.append([
            InlineKeyboardButton(
                text=f"{'✓ ' if level == selected_level else ''}{level}",
                callback_data=f"ai_level:{level}",
            )
            for level in ("N5", "N4", "N3", "N2", "N1")
        ])
        rows.append([InlineKeyboardButton(
            text="✏️ Изменить комментарий" if has_comment else "✏️ Добавить комментарий",
            callback_data="ai_comment_request",
        )])
        if has_comment:
            rows.append([InlineKeyboardButton(
                text="🗑 Убрать комментарий", callback_data="ai_comment_clear"
            )])
    rows.append([InlineKeyboardButton(
        text="← Панель администратора", callback_data="admin_home"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ai_topic_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 Опубликовать", callback_data="ai_publish"
        )],
        [InlineKeyboardButton(
            text="🔄 Перегенерировать", callback_data="ai_regenerate"
        )],
        [InlineKeyboardButton(text="✖ Отменить", callback_data="ai_cancel")],
    ])


def ai_comment_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✖ Отменить", callback_data="ai_comment_cancel"
        )
    ]])


def ai_revision_cancel_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✖ Отменить исправление",
            callback_data=f"ai_queue_revision_cancel:{post_id}",
        )
    ]])


def _navigation_row(prefix: str, page: int, pages: int) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton(
            text="← Назад", callback_data=f"{prefix}:{page - 1}"
        ))
    row.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        row.append(InlineKeyboardButton(
            text="Вперёд →", callback_data=f"{prefix}:{page + 1}"
        ))
    return row


def available_events_keyboard(
    events: list[dict], show_admin_return: bool = False
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"🎟 {event_title(event)[:48]}",
        callback_data=f"register_event:{event['post_id']}",
    )] for event in events]
    rows.append([InlineKeyboardButton(text="⌂ Главное меню", callback_data="user_home")])
    if show_admin_return:
        rows.append([InlineKeyboardButton(
            text="⚙️ Панель администратора", callback_data="admin_home"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_events_keyboard(
    events: list[dict], show_admin_return: bool = False
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"✖ Отменить · {event_title(event)[:38]}",
        callback_data=f"unregister:{event['post_id']}",
    )] for event in events]
    rows.append([InlineKeyboardButton(text="⌂ Главное меню", callback_data="user_home")])
    if show_admin_return:
        rows.append([InlineKeyboardButton(
            text="⚙️ Панель администратора", callback_data="admin_home"
        )])
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
    if past:
        rows.append(_navigation_row("admin_events_page:past", page, pages))
    rows.append([InlineKeyboardButton(
        text="Активные мероприятия" if past else "Прошедшие мероприятия",
        callback_data="admin_events_page:active:0" if past else "admin_events_page:past:0",
    )])
    rows.append([InlineKeyboardButton(
        text="← Мероприятия и публикации", callback_data="admin_events_menu"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def participants_keyboard(
    post_id: int, page: int, pages: int
) -> InlineKeyboardMarkup:
    rows = [_navigation_row(f"participants:{post_id}", page, pages)]
    rows.append([InlineKeyboardButton(
        text="← Мероприятия", callback_data="admin_registrations"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_keyboard(
    show_admin_return: bool = False, feedback_enabled: bool = True
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data="edit_profile")],
        [InlineKeyboardButton(
            text="💬 Оставить обратную связь", callback_data="feedback_manual"
        )],
        [InlineKeyboardButton(
            text=(
                "💬 Предлагать отзывы: ✅"
                if feedback_enabled else "💬 Предлагать отзывы: ❌"
            ),
            callback_data="feedback_toggle",
        )],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="user_home")],
    ]
    if show_admin_return:
        rows.append([InlineKeyboardButton(
            text="⚙️ Панель администратора", callback_data="admin_home"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_answer_keyboard(field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"profile_answer:{field}:1"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"profile_answer:{field}:0"),
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


def feedback_offer_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Да", callback_data=f"feedback_offer:{post_id}:yes"
            ),
            InlineKeyboardButton(
                text="Нет", callback_data=f"feedback_offer:{post_id}:no"
            ),
        ],
        [InlineKeyboardButton(
            text="Никогда не спрашивать больше",
            callback_data=f"feedback_offer:{post_id}:never",
        )],
    ])


def feedback_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Пропустить", callback_data="feedback_skip"
    )]])


def admin_feedbacks_keyboard(
    feedback_entries: list[dict], page: int, pages: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for entry in feedback_entries:
        author = (
            entry.get("full_name")
            or entry.get("telegram_username")
            or f"Пользователь {entry['user_id']}"
        )
        rows.append([InlineKeyboardButton(
            text=f"Отзыв #{entry['id']} · {author[:42]}",
            callback_data=f"admin_feedback_item:{entry['id']}:{page}",
        )])
    rows.append(_navigation_row("admin_feedback_page", page, pages))
    rows.append([InlineKeyboardButton(
        text="← Панель администратора", callback_data="admin_home"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_feedback_detail_keyboard(feedback_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="← К отзывам", callback_data=f"admin_feedback_page:{page}"
        )],
        [InlineKeyboardButton(
            text="← Панель администратора", callback_data="admin_home"
        )],
    ])


def confirm_event_cancellation_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Да, отменить мероприятие",
            callback_data=f"confirm_cancel_event:{post_id}",
        )],
        [InlineKeyboardButton(text="Нет", callback_data="dismiss_cancel_event")],
    ])
