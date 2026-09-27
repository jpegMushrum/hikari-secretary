from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..access import AdminAccess
from ..keyboards import (
    admin_events_menu_keyboard,
    admin_menu_keyboard,
    user_menu_keyboard,
)
from ..runtime import AppContext
from .registrations import RegistrationHandlers


class CoreHandlers:
    def __init__(
        self,
        context: AppContext,
        access: AdminAccess,
        registrations: RegistrationHandlers,
    ):
        self.context = context
        self.access = access
        self.registrations = registrations

    def register(self, router: Router) -> None:
        router.message.register(self.start, CommandStart())
        router.message.register(self.help, Command("help"))
        router.callback_query.register(
            self.show_user_interface, F.data == "show_user_interface"
        )
        router.callback_query.register(self.new_post, F.data == "admin_new_post")
        router.callback_query.register(
            self.admin_events_menu, F.data == "admin_events_menu"
        )
        router.callback_query.register(self.help_button, F.data == "admin_help")
        router.callback_query.register(self.user_home, F.data == "user_home")
        router.callback_query.register(self.admin_home, F.data == "admin_home")

    async def start(self, message: Message) -> None:
        if not message.from_user or message.chat.type != "private":
            return
        payload = (message.text or "").partition(" ")[2].strip()
        if payload.startswith("event_") and payload[6:].isdigit():
            await self.registrations.begin_registration(
                message.from_user, message.answer, int(payload[6:])
            )
            return
        if not self.access.is_admin(message.from_user.id):
            await self._send_user_home(message.answer, False)
            return
        await self._send_admin_home(message.answer)

    async def _send_admin_home(self, send) -> None:
        await send(
            "⚙️ Панель администратора\n\n"
            "Выберите раздел: мероприятия и публикации либо генерация материалов через ИИ.\n\n"
            "/events — мои личные регистрации\n"
            "/profile — настройка пользовательского профиля\n"
            "/help — помощь",
            reply_markup=admin_menu_keyboard(),
        )

    async def _send_admin_events_menu(self, send) -> None:
        await send(
            "📅 Мероприятия и публикации\n\n"
            "Здесь можно создать публикацию, посмотреть очередь и управлять "
            "мероприятиями и участниками.",
            reply_markup=admin_events_menu_keyboard(),
        )

    async def _send_user_home(self, send, is_admin: bool) -> None:
        await send(
            "👋 Главное меню\n\n"
            "Здесь можно найти мероприятие, управлять регистрациями и настроить профиль.",
            reply_markup=user_menu_keyboard(show_admin_return=is_admin),
        )

    async def show_user_interface(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._send_user_home(callback.message.answer, True)
        await callback.answer()

    async def user_home(self, callback: CallbackQuery) -> None:
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer("Откройте личные сообщения с ботом", show_alert=True)
            return
        await self._send_user_home(
            callback.message.edit_text,
            self.access.is_admin(callback.from_user.id),
        )
        await callback.answer()

    async def admin_home(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._send_admin_home(callback.message.edit_text)
        await callback.answer()

    async def admin_events_menu(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._send_admin_events_menu(callback.message.edit_text)
        await callback.answer()

    async def new_post(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await callback.message.answer(
            "Отправьте текст, фотографию с подписью, альбом или Rich Message. "
            "Я создам черновик и покажу настройки публикации."
        )
        await callback.answer()

    async def help_button(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await self._send_help(callback.message.answer)
        await callback.answer()

    async def help(self, message: Message) -> None:
        if not await self.access.guard_message(message):
            return
        await self._send_help(message.answer)

    async def _send_help(self, send) -> None:
        await send(
            "Поддерживаются текст, ссылки, изображения и Rich Messages. "
            "Оформление Telegram сохраняется. "
            "К публикации можно добавить регистрацию на мероприятие. "
            "Время вводится в формате ДД.ММ.ГГГГ ЧЧ:ММ "
            f"({self.context.settings.timezone_name})."
        )
