"""Resolve Telegram chat and channel IDs."""

from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import parse_qs, urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Chat, Update, User


def normalize_telegram_reference(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        username = value[1:]
    elif "://" not in value and "/" not in value:
        username = value
    else:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme == "tg" and parsed.netloc == "resolve":
            username = parse_qs(parsed.query).get("domain", [""])[0]
        elif host in {"t.me", "telegram.me"}:
            parts = [part for part in parsed.path.split("/") if part]
            if not parts or parts[0] in {"joinchat", "c", "s"} or parts[0].startswith("+"):
                raise ValueError("нужна публичная ссылка вида https://t.me/username")
            username = parts[0]
        else:
            raise ValueError("поддерживаются @username, t.me/username и tg://resolve?domain=username")
    if not username or not username.replace("_", "").isalnum():
        raise ValueError("некорректный публичный username")
    return f"@{username}"


def describe_user(user: User | None) -> str | None:
    if user is None:
        return None
    label = " ".join(part for part in (user.first_name, user.last_name) if part)
    username = f"@{user.username}" if user.username else "без username"
    return f"ПОЛЬЗОВАТЕЛЬ: {label or 'без имени'} | {username} | ID={user.id}"


def describe_chat(chat: Chat) -> str:
    title = chat.title or chat.full_name or "без названия"
    username = f"@{chat.username}" if chat.username else "без username"
    return f"TELEGRAM: {title} | тип={chat.type} | {username} | chat_id={chat.id}"


async def resolve_telegram(bot: Bot, references: list[str]) -> bool:
    failed = False
    for source in references:
        try:
            username = normalize_telegram_reference(source)
            chat = await bot.get_chat(username)
            print(f"{source} -> {describe_chat(chat)}")
        except ValueError as exc:
            failed = True
            print(f"{source} -> ошибка: {exc}")
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            failed = True
            print(
                f"{source} -> не найдено. Нужна публичная группа или канал. "
                f"Ответ Telegram: {exc.message}"
            )
    return failed


async def listen_for_telegram_ids(bot: Bot) -> None:
    offset: int | None = None
    print("Режим прослушивания Telegram запущен.", flush=True)
    print("Добавьте бота в чат и отправьте там сообщение. Остановка: Ctrl+C.\n", flush=True)
    while True:
        updates = await bot.get_updates(
            offset=offset,
            timeout=30,
            allowed_updates=["message", "channel_post", "my_chat_member"],
        )
        for update in updates:
            offset = update.update_id + 1
            message = update.message or update.channel_post
            membership = update.my_chat_member
            chat = message.chat if message else membership.chat if membership else None
            user = message.from_user if message else membership.from_user if membership else None
            if chat:
                print(describe_chat(chat), flush=True)
            if message and message.message_thread_id:
                print(f"ТОПИК: message_thread_id={message.message_thread_id}", flush=True)
            if user:
                print(describe_user(user), flush=True)
            if chat or user:
                print("-" * 60, flush=True)


async def run(telegram_refs: list[str], listen: bool) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Ошибка: переменная TELEGRAM_BOT_TOKEN не задана")
        return 2

    bot = Bot(token)
    try:
        failed = await resolve_telegram(bot, telegram_refs) if telegram_refs else False
        if listen:
            await listen_for_telegram_ids(bot)
    finally:
        await bot.session.close()
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Получить ID Telegram-каналов и чатов.")
    parser.add_argument("--telegram", nargs="*", default=[], help="@username или t.me-ссылки")
    parser.add_argument("--listen", action="store_true", help="Слушать события для определения приватного chat_id")
    args = parser.parse_args()
    if not args.telegram and not args.listen:
        parser.error("укажите --telegram или --listen")
    raise SystemExit(asyncio.run(run(args.telegram, args.listen)))


if __name__ == "__main__":
    main()
