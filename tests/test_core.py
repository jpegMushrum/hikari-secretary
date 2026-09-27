import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.access import AdminAccess
from app.handlers.core import CoreHandlers


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

    def test_user_cannot_open_admin_user_interface_button(self) -> None:
        context = self._context(100)
        handlers = CoreHandlers(context, AdminAccess(context), SimpleNamespace())
        callback = self._callback(200)

        asyncio.run(handlers.show_user_interface(callback))

        callback.message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once_with("Доступ запрещён", show_alert=True)


if __name__ == "__main__":
    unittest.main()
