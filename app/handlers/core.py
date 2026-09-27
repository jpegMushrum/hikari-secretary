from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..access import AdminAccess
from ..keyboards import admin_menu_keyboard, user_menu_keyboard
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
            await message.answer(
                "Здесь можно зарегистрироваться на мероприятие и управлять своими регистрациями.",
                reply_markup=user_menu_keyboard(),
            )
            return
        await message.answer(
            "Отправьте текст, фотографию с подписью или альбом. Затем выберите цели и время публикации.\n\n"
            "/queue — запланированные публикации\n"
            "/registrations — мероприятия и участники\n"
            "/events — мои личные регистрации\n"
            "/profile — настройка пользовательского профиля\n"
            "/help — помощь",
            reply_markup=admin_menu_keyboard(),
        )

    async def show_user_interface(self, callback: CallbackQuery) -> None:
        if not await self.access.guard_callback(callback):
            return
        await callback.message.answer(
            "Пользовательский интерфейс. Здесь вы можете зарегистрироваться на "
            "мероприятие и управлять своими регистрациями.",
            reply_markup=user_menu_keyboard(),
        )
        await callback.answer()

    async def help(self, message: Message) -> None:
        if not await self.access.guard_message(message):
            return
        await message.answer(
            "Поддерживаются текст, ссылки, изображения и Rich Messages. "
            "Оформление Telegram сохраняется. "
            "К публикации можно добавить регистрацию на мероприятие. "
            "Время вводится в формате ДД.ММ.ГГГГ ЧЧ:ММ "
            f"({self.context.settings.timezone_name})."
        )
