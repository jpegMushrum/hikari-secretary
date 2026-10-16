import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.access import AdminAccess
from app.handlers.registrations import RegistrationHandlers
from app.db import Page
from app.keyboards import (
    admin_statistics_keyboard,
    feedback_offer_keyboard,
    participants_keyboard,
    profile_keyboard,
    user_menu_keyboard,
)
from app.presentation import (
    admin_events_rich_message,
    feedbacks_rich_message,
    participant_status_label,
    people_statistics_rich_message,
    participants_rich_message,
    reminder_offset_label,
    telegram_profile_label,
)


def make_access(*admin_ids: int) -> AdminAccess:
    context = SimpleNamespace(settings=SimpleNamespace(admin_ids=frozenset(admin_ids)))
    return AdminAccess(context)


def make_message(user_id: int | None, chat_type: str = "private") -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id) if user_id is not None else None,
        chat=SimpleNamespace(id=100, type=chat_type),
        content_type="text",
        answer=AsyncMock(),
    )


class AccessAndPresentationTests(unittest.TestCase):
    def test_non_admin_message_is_silently_ignored(self) -> None:
        access = make_access(1)
        message = make_message(2)

        allowed = asyncio.run(access.guard_message(message))

        self.assertFalse(allowed)
        message.answer.assert_not_awaited()

    def test_admin_group_message_is_silently_ignored(self) -> None:
        access = make_access(1)
        message = make_message(1, "group")

        allowed = asyncio.run(access.guard_message(message))

        self.assertFalse(allowed)
        message.answer.assert_not_awaited()

    def test_admin_private_message_is_allowed(self) -> None:
        access = make_access(1)
        message = make_message(1)

        allowed = asyncio.run(access.guard_message(message))

        self.assertTrue(allowed)
        message.answer.assert_not_awaited()

    def test_reminder_offset_is_human_readable(self) -> None:
        self.assertEqual(reminder_offset_label(30), "за 30 мин.")
        self.assertEqual(reminder_offset_label(120), "за 2 ч.")
        self.assertEqual(reminder_offset_label(1440), "за 1 дн.")

    def test_telegram_profile_prefers_username(self) -> None:
        self.assertEqual(
            telegram_profile_label({
                "telegram_username": "ivan",
                "telegram_first_name": "Ваня",
                "telegram_last_name": None,
            }),
            "@ivan",
        )

    def test_telegram_profile_falls_back_to_display_name(self) -> None:
        self.assertEqual(
            telegram_profile_label({
                "telegram_username": None,
                "telegram_first_name": "Пирожок",
                "telegram_last_name": "Японский",
            }),
            "Пирожок Японский",
        )

    def test_participant_table_uses_rich_message_table_block(self) -> None:
        message = participants_rich_message(
            7,
            "Осенний вечер японского языка",
            [{
                "full_name": "Анна Петрова",
                "telegram_username": None,
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "status": "cancelled",
                "attended": None,
                "registered_at": datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc).isoformat(),
                "cancelled_at": datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc).isoformat(),
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
            }],
            0,
            1,
            ZoneInfo("Europe/Moscow"),
        )

        table = message.blocks[1]
        self.assertEqual(
            message.blocks[0].text,
            "Участники мероприятия #7: «Осенний вечер японского языка»",
        )
        self.assertEqual(table.type, "table")
        self.assertEqual(table.cells[0][0].text, "ФИО")
        self.assertEqual(table.cells[1][1].text, "Анна Петрова")
        self.assertEqual(table.cells[1][2].text, "отменён")
        self.assertEqual(table.cells[1][3].text, "✅")
        self.assertEqual(table.cells[1][4].text, "❌")
        self.assertEqual(table.cells[1][5].text, "02.10.2026 13:00")
        self.assertEqual(table.cells[0][5].text, "Время\nрег./отм.")

        callbacks = {
            button.callback_data
            for row in participants_keyboard(7, 0, 2, "pass").inline_keyboard
            for button in row
        }
        self.assertEqual(
            {
                "participants:7:name:0",
                "participants:7:pass:0",
                "participants:7:registered_at:0",
                "participants:7:pass:1",
                "noop",
                "admin_registrations",
            },
            callbacks,
        )

    def test_admin_event_tables_show_active_and_past_events(self) -> None:
        event = {
            "post_id": 7,
            "title": "Осенний вечер японского языка",
            "text": "Описание мероприятия",
            "starts_at": "2026-10-15T14:00:00+00:00",
            "ends_at": "2026-10-15T16:00:00+00:00",
            "registrations": 12,
        }
        active = admin_events_rich_message(
            [event], False, 0, 1, ZoneInfo("Europe/Moscow")
        )
        past = admin_events_rich_message(
            [event], True, 1, 3, ZoneInfo("Europe/Moscow")
        )

        table = active.blocks[1]
        self.assertEqual(active.blocks[0].text, "Активные мероприятия")
        self.assertEqual(table.type, "table")
        self.assertEqual(table.cells[0][0].text, "#")
        self.assertEqual(table.cells[1][0].text, "7")
        self.assertEqual(table.cells[1][1].text, "Осенний вечер японского языка")
        self.assertEqual(table.cells[1][2].text, "15.10.2026 17:00")
        self.assertEqual(table.cells[1][3].text, "15.10.2026 19:00")
        self.assertEqual(table.cells[1][4].text, "12")
        self.assertEqual(past.blocks[0].text, "Прошедшие мероприятия")
        self.assertEqual(past.blocks[1].caption, "Страница 2/3")

    def test_participant_statuses_are_human_readable(self) -> None:
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": None}),
            "зарегистрирован",
        )
        self.assertEqual(
            participant_status_label({"status": "cancelled", "attended": None}),
            "отменён",
        )
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": 1}),
            "был",
        )
        self.assertEqual(
            participant_status_label({"status": "registered", "attended": 0}),
            "не был",
        )

    def test_feedback_offer_and_profile_setting_are_visible(self) -> None:
        offer_callbacks = {
            button.callback_data
            for row in feedback_offer_keyboard(7).inline_keyboard
            for button in row
        }
        self.assertEqual(offer_callbacks, {
            "feedback_offer:7:yes",
            "feedback_offer:7:no",
            "feedback_offer:7:never",
        })
        profile_buttons = {
            button.text: button.callback_data
            for row in profile_keyboard(feedback_enabled=False).inline_keyboard
            for button in row
        }
        self.assertEqual(
            profile_buttons["💬 Предлагать отзывы: ❌"], "feedback_toggle"
        )
        self.assertNotIn("💬 Оставить обратную связь", profile_buttons)
        user_buttons = {
            button.text: button.callback_data
            for row in user_menu_keyboard().inline_keyboard
            for button in row
        }
        self.assertEqual(
            user_buttons["💬 Оставить обратную связь"], "feedback_manual"
        )

    def test_feedback_table_shows_author_event_and_manual_marker(self) -> None:
        message = feedbacks_rich_message(
            [
                {
                    "id": 2,
                    "user_id": 200,
                    "post_id": 7,
                    "title": "Осенний вечер",
                    "post_text": "Описание",
                    "full_name": "Анна Петрова",
                    "telegram_username": "anna",
                    "telegram_first_name": "Анна",
                    "telegram_last_name": "Петрова",
                    "created_at": "2026-10-15T14:00:00+00:00",
                    "feedback_text": "Очень понравилось!",
                },
                {
                    "id": 1,
                    "user_id": 201,
                    "post_id": None,
                    "title": None,
                    "post_text": None,
                    "full_name": "Иван Иванов",
                    "telegram_username": None,
                    "telegram_first_name": "Иван",
                    "telegram_last_name": "Иванов",
                    "created_at": "2026-10-15T13:00:00+00:00",
                    "feedback_text": "Общий отзыв",
                },
            ],
            0,
            1,
            ZoneInfo("Europe/Moscow"),
        )

        table = message.blocks[1]
        self.assertEqual(message.blocks[0].text, "Отзывы")
        self.assertEqual(table.type, "table")
        self.assertEqual(table.cells[0][0].text, "Автор")
        self.assertEqual(table.cells[1][0].text, "Анна Петрова (@anna)")
        self.assertEqual(table.cells[1][1].text, "Мероприятие #7: «Осенний вечер»")
        self.assertEqual(table.cells[1][2].text, "15.10.2026 17:00")
        self.assertEqual(table.cells[2][1].text, "Общий отзыв (мероприятие не указано)")

    def test_people_statistics_uses_rich_message_table_and_sort_controls(self) -> None:
        message = people_statistics_rich_message(
            [{
                "user_id": 200,
                "full_name": "Анна Петрова",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
                "visits": 3,
                "feedback_count": 2,
                "last_visited_at": "2026-10-15T14:00:00+00:00",
            }],
            0,
            1,
            "visits",
            ZoneInfo("Europe/Moscow"),
        )

        table = message.blocks[1]
        self.assertEqual(message.blocks[0].text, "Статистика людей")
        self.assertEqual(table.type, "table")
        self.assertEqual(table.cells[0][4].text, "Посещ.")
        self.assertEqual(table.cells[1][1].text, "@anna")
        self.assertEqual(table.cells[1][2].text, "✅")
        self.assertEqual(table.cells[1][3].text, "❌")
        self.assertEqual(table.cells[1][4].text, "3")
        self.assertEqual(table.cells[1][5].text, "2")
        self.assertEqual(table.cells[1][6].text, "15.10.2026 17:00")

        callbacks = {
            button.callback_data
            for row in admin_statistics_keyboard("visits", 0, 2).inline_keyboard
            for button in row
        }
        self.assertEqual(
            {
                "admin_statistics:name:0",
                "admin_statistics:visits:0",
                "admin_statistics:last_visit:0",
                "admin_statistics:visits:1",
                "admin_home",
                "noop",
            },
            callbacks,
        )

    def test_participant_table_is_sent_only_after_admin_guard(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(event_registrations_page=AsyncMock(return_value=Page([{
                "full_name": "Анна Петрова",
                "title": "Осенний вечер японского языка",
                "text": "Описание мероприятия",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "status": "registered",
                "attended": None,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_at": None,
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
            }], 0, 10, 1))),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="participants:7",
            message=SimpleNamespace(chat=SimpleNamespace(id=1), answer=AsyncMock()),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.show_participants(callback))

        context.db.event_registrations_page.assert_awaited_once_with(7, 0, sort_by="name")
        context.bot.send_rich_message.assert_awaited_once()
        self.assertEqual(
            context.bot.send_rich_message.await_args.args[1].blocks[1].type,
            "table",
        )
        callback.answer.assert_awaited_once()

    def test_admin_events_are_sent_as_rich_table(self) -> None:
        event = {
            "post_id": 7,
            "title": "Осенний вечер японского языка",
            "text": "Описание мероприятия",
            "starts_at": "2026-10-15T14:00:00+00:00",
            "ends_at": "2026-10-15T16:00:00+00:00",
            "registrations": 12,
        }
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(admin_events=AsyncMock(return_value=[event])),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=1)),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.admin_registrations_button(callback))

        context.db.admin_events.assert_awaited_once_with()
        context.bot.send_rich_message.assert_awaited_once()
        rich_message = context.bot.send_rich_message.await_args.args[1]
        self.assertEqual(rich_message.blocks[1].type, "table")
        self.assertEqual(
            rich_message.blocks[0].text, "Активные мероприятия"
        )
        callback.answer.assert_awaited_once()

    def test_past_event_page_replaces_previous_rich_table(self) -> None:
        event = {
            "post_id": 7,
            "title": "Осенний вечер японского языка",
            "text": "Описание мероприятия",
            "starts_at": "2026-10-15T14:00:00+00:00",
            "ends_at": "2026-10-15T16:00:00+00:00",
            "registrations": 12,
        }
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(
                admin_events_page=AsyncMock(return_value=Page([event], 1, 5, 6)),
            ),
            bot=SimpleNamespace(
                send_rich_message=AsyncMock(), delete_message=AsyncMock(),
            ),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="admin_events_page:past:1",
            message=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=24),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.paginate_admin_events(callback))

        context.db.admin_events_page.assert_awaited_once_with(True, 1)
        context.bot.send_rich_message.assert_awaited_once()
        context.bot.delete_message.assert_awaited_once_with(1, 24)
        callback.answer.assert_awaited_once()

    def test_participant_sort_replaces_previous_rich_table(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(event_registrations_page=AsyncMock(return_value=Page([{
                "full_name": "Анна Петрова",
                "title": "Осенний вечер японского языка",
                "text": "Описание мероприятия",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "status": "registered",
                "attended": None,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_at": None,
                "is_russian_citizen": 0,
                "is_itmo_student": 1,
            }], 0, 10, 1))),
            bot=SimpleNamespace(
                send_rich_message=AsyncMock(), delete_message=AsyncMock(),
            ),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="participants:7:pass:0",
            message=SimpleNamespace(
                chat=SimpleNamespace(id=1), message_id=22, answer=AsyncMock(),
            ),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.show_participants(callback))

        context.db.event_registrations_page.assert_awaited_once_with(7, 0, sort_by="pass")
        context.bot.send_rich_message.assert_awaited_once()
        context.bot.delete_message.assert_awaited_once_with(1, 22)
        callback.answer.assert_awaited_once()

    def test_attendance_confirmation_offers_feedback_only_after_visit(self) -> None:
        db = SimpleNamespace(
            record_attendance=AsyncMock(return_value=True),
            feedback_enabled=AsyncMock(return_value=True),
        )
        handlers = RegistrationHandlers(SimpleNamespace(db=db), None)
        callback = SimpleNamespace(
            data="attendance:7:1",
            from_user=SimpleNamespace(id=200),
            message=SimpleNamespace(
                chat=SimpleNamespace(type="private"),
                edit_text=AsyncMock(),
                answer=AsyncMock(),
            ),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.record_attendance(callback))

        db.record_attendance.assert_awaited_once_with(200, 7, True)
        db.feedback_enabled.assert_awaited_once_with(200)
        self.assertEqual(
            callback.message.answer.await_args.args[0],
            "Хотите оставить обратную связь?",
        )
        callback.answer.assert_awaited_once()

    def test_statistics_table_is_sent_only_after_admin_guard(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(people_statistics_page=AsyncMock(return_value=Page([{
                "user_id": 200,
                "full_name": "Анна Петрова",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "is_russian_citizen": 1,
                "is_itmo_student": 0,
                "visits": 3,
                "feedback_count": 2,
                "last_visited_at": None,
            }], 0, 10, 1))),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="admin_statistics",
            message=SimpleNamespace(chat=SimpleNamespace(id=1, type="private")),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.show_admin_statistics(callback))

        context.db.people_statistics_page.assert_awaited_once_with("name", 0)
        context.bot.send_rich_message.assert_awaited_once()
        self.assertEqual(
            context.bot.send_rich_message.await_args.args[1].blocks[1].type,
            "table",
        )
        callback.answer.assert_awaited_once()

    def test_statistics_sort_replaces_previous_rich_table(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(people_statistics_page=AsyncMock(return_value=Page([], 0, 10, 0))),
            bot=SimpleNamespace(
                send_rich_message=AsyncMock(), delete_message=AsyncMock(),
            ),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            data="admin_statistics:visits:0",
            message=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=23),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.paginate_admin_statistics(callback))

        context.db.people_statistics_page.assert_awaited_once_with("visits", 0)
        context.bot.send_rich_message.assert_awaited_once()
        context.bot.delete_message.assert_awaited_once_with(1, 23)
        callback.answer.assert_awaited_once()

    def test_feedback_table_is_sent_only_after_admin_guard(self) -> None:
        context = SimpleNamespace(
            settings=SimpleNamespace(timezone=ZoneInfo("Europe/Moscow")),
            db=SimpleNamespace(feedback_entries_page=AsyncMock(return_value=Page([{
                "id": 4,
                "user_id": 200,
                "post_id": None,
                "title": None,
                "post_text": None,
                "full_name": "Анна Петрова",
                "telegram_username": "anna",
                "telegram_first_name": "Анна",
                "telegram_last_name": "Петрова",
                "created_at": "2026-10-15T14:00:00+00:00",
                "feedback_text": "Очень понравилось!",
            }], 0, 5, 1))),
            bot=SimpleNamespace(send_rich_message=AsyncMock()),
        )
        access = SimpleNamespace(guard_callback=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(context, access)
        callback = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(id=1, type="private")),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.show_admin_feedback(callback))

        context.db.feedback_entries_page.assert_awaited_once_with(0)
        context.bot.send_rich_message.assert_awaited_once()
        self.assertEqual(
            context.bot.send_rich_message.await_args.args[1].blocks[1].type,
            "table",
        )
        callback.answer.assert_awaited_once()

    def test_feedback_offer_starts_event_feedback_flow(self) -> None:
        db = SimpleNamespace(begin_feedback_flow=AsyncMock(return_value=True))
        handlers = RegistrationHandlers(SimpleNamespace(db=db), None)
        callback = SimpleNamespace(
            data="feedback_offer:7:yes",
            from_user=SimpleNamespace(id=200),
            message=SimpleNamespace(
                chat=SimpleNamespace(type="private"), edit_text=AsyncMock()
            ),
            answer=AsyncMock(),
        )

        asyncio.run(handlers.answer_feedback_offer(callback))

        db.begin_feedback_flow.assert_awaited_once_with(200, 7)
        self.assertIn(
            "Напишите отзыв", callback.message.edit_text.await_args.args[0]
        )
        callback.answer.assert_awaited_once()

    def test_text_feedback_is_saved_from_active_flow(self) -> None:
        db = SimpleNamespace(
            registration_flow=AsyncMock(return_value=None),
            profile_edit_flow=AsyncMock(return_value=None),
            feedback_flow=AsyncMock(return_value={"post_id": None}),
            save_feedback_from_flow=AsyncMock(return_value={"id": 1, "post_id": None}),
        )
        handlers = RegistrationHandlers(SimpleNamespace(db=db), None)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=200),
            chat=SimpleNamespace(type="private"),
            text="Общий отзыв",
            answer=AsyncMock(),
        )

        handled = asyncio.run(handlers.handle_text_flow(message))

        self.assertTrue(handled)
        db.save_feedback_from_flow.assert_awaited_once_with(200, "Общий отзыв")
        self.assertEqual(message.answer.await_args.args[0], "Спасибо за отзыв!")
