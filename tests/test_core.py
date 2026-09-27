import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.access import AdminAccess
from app.bot import SecretaryBot
from app.handlers.core import CoreHandlers
from app.keyboards import admin_menu_keyboard


class CoreHandlersTests(unittest.TestCase):
    @staticmethod
    def _context(*admin_ids: int) -> SimpleNamespace:
        return SimpleNamespace(
            settings=SimpleNamespace(admin_ids=frozenset(admin_ids))
        )

    @staticmethod
    def _callback(user_id: int) -> SimpleNamespace:
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=user_id, type="private"),
                answer=AsyncMock(),
            ),
            data="show_user_interface",
            answer=AsyncMock(),
        )

    def test_admin_can_open_user_interface(self) -> None:
        context = self._context(100)
        handlers = CoreHandlers(context, AdminAccess(context), SimpleNamespace())
        callback = self._callback(100)

        asyncio.run(handlers.show_user_interface(callback))

        callback.message.answer.assert_awaited_once()
        markup = callback.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(
            markup.inline_keyboard[0][0].callback_data,
            "available_events",
        )
        callback.answer.assert_awaited_once_with()

    def test_admin_menu_exposes_primary_actions(self) -> None:
        callbacks = {
            button.callback_data
            for row in admin_menu_keyboard().inline_keyboard
            for button in row
        }
        self.assertEqual(callbacks, {
            "admin_new_post",
            "admin_queue",
            "admin_registrations",
            "show_user_interface",
            "admin_help",
        })

    def test_user_cannot_open_admin_user_interface_button(self) -> None:
        context = self._context(100)
        handlers = CoreHandlers(context, AdminAccess(context), SimpleNamespace())
        callback = self._callback(200)

        asyncio.run(handlers.show_user_interface(callback))

        callback.message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Доступ запрещён", show_alert=True)


class TelegramMenuTests(unittest.TestCase):
    def test_command_menu_contains_start_for_users_and_admins(self) -> None:
        bot = SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_chat_menu_button=AsyncMock(),
        )
        secretary = object.__new__(SecretaryBot)
        secretary.context = SimpleNamespace(
            bot=bot,
            settings=SimpleNamespace(admin_ids=frozenset({100})),
        )

        asyncio.run(secretary._configure_telegram_menu())

        self.assertEqual(bot.set_my_commands.await_count, 2)
        for call in bot.set_my_commands.await_args_list:
            self.assertEqual(call.args[0][0].command, "start")
        bot.set_chat_menu_button.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
