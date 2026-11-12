"""Telegram-бот (aiogram 3): отвечает только пользователям из белого списка, остальных молча игнорирует."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.access import is_admin, is_allowed, parse_user_id
from app.config import Config
from app.engine import Engine
from app.llm import LLMError, describe
from app.retrieval import Retriever
from app.state import State

log = logging.getLogger("tg-channel")

HELP = (
    "Задайте вопрос — найду ответ в архиве канала и приложу ссылки на посты.\n\n"
    "/short /mid /long — длина ответов\n"
    "/again — ответить на последний вопрос заново\n"
    "/forget — забыть историю диалога\n"
    "/help — эта справка"
)
ADMIN_HELP = (
    "\n\nАдмину:\n"
    "/add <id> /remove <id> — доступ пользователю\n"
    "/users — список доступа\n"
    "/status — модель и база\n"
    "/stats — статистика"
)
LIMIT = 4000

RATE = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="👍", callback_data="rate:1"),
    InlineKeyboardButton(text="👎", callback_data="rate:0"),
]])


def chunks(text: str, size: int = LIMIT) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def build_router(cfg: Config, store, state: State, engine: Engine) -> Router:
    router = Router()
    allowed = F.from_user.func(lambda u: is_allowed(cfg, state, u.id))
    admin = F.from_user.func(lambda u: is_admin(cfg, u.id))
    router.message.filter(allowed)
    router.callback_query.filter(allowed)

    async def reply(message: Message, question: str) -> None:
        uid = message.from_user.id
        await message.bot.send_chat_action(message.chat.id, "typing")
        try:
            text = await asyncio.to_thread(engine.answer, uid, question)
        except LLMError:
            log.exception("llm error")
            await message.answer("Модель сейчас недоступна, попробуйте позже.")
            return
        parts = chunks(text)
        for part in parts[:-1]:
            await message.answer(part, disable_web_page_preview=True)
        await message.answer(parts[-1], disable_web_page_preview=True, reply_markup=RATE)

    @router.message(Command("start", "help", "menu"))
    async def help_(message: Message) -> None:
        await message.answer(HELP + (ADMIN_HELP if is_admin(cfg, message.from_user.id) else ""))

    @router.message(Command("forget"))
    async def forget(message: Message) -> None:
        state.forget(message.from_user.id)
        await message.answer("История диалога очищена.")

    @router.message(Command("short", "mid", "long"))
    async def length(message: Message, command: CommandObject) -> None:
        state.set_length(message.from_user.id, command.command)
        await message.answer({"short": "Буду отвечать коротко.", "mid": "Средняя длина ответов.",
                              "long": "Буду отвечать подробно."}[command.command])

    @router.message(Command("again"))
    async def again(message: Message) -> None:
        question = state.last_question(message.from_user.id)
        if not question:
            await message.answer("Пока не было вопросов.")
            return
        await reply(message, question)

    @router.message(Command("add"), admin)
    async def add(message: Message, command: CommandObject) -> None:
        uid = parse_user_id(command.args)
        if uid is None:
            await message.answer("Формат: /add <числовой id>")
            return
        state.add_user(uid)
        await message.answer(f"Доступ выдан: {uid}")

    @router.message(Command("remove"), admin)
    async def remove(message: Message, command: CommandObject) -> None:
        uid = parse_user_id(command.args)
        if uid is None:
            await message.answer("Формат: /remove <числовой id>")
            return
        if uid in cfg.allowed_user_ids or uid in cfg.admin_ids:
            await message.answer("Этот id задан в .env — уберите его оттуда.")
            return
        await message.answer("Доступ снят." if state.remove_user(uid) else "Такого id нет в списке.")

    @router.message(Command("users"), admin)
    async def users(message: Message) -> None:
        def fmt(ids) -> str:
            return ", ".join(str(i) for i in sorted(ids)) or "—"
        await message.answer(f"Админы: {fmt(cfg.admin_ids)}\nИз .env: {fmt(cfg.allowed_user_ids)}\n"
                             f"Добавлены через /add: {fmt(state.users())}")

    @router.message(Command("status"), admin)
    async def status(message: Message) -> None:
        count, last = store.stats()
        await message.answer(f"Модель: {describe(cfg)}\nКанал: {cfg.channel}\n"
                             f"Сообщений в базе: {count}\nПоследний id: {last}")

    @router.message(Command("stats"), admin)
    async def stats(message: Message) -> None:
        s = state.stats()
        await message.answer(f"Вопросов: {s['asked']}\nДиалогов: {s['users_with_history']}\n"
                             f"Добавлено пользователей: {s['added_users']}\n👍 {s['up']}  👎 {s['down']}")

    @router.callback_query(F.data.startswith("rate:"))
    async def rate(query: CallbackQuery) -> None:
        state.feedback(query.data == "rate:1")
        await query.answer("Спасибо!")
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)

    @router.message(F.text & ~F.text.startswith("/"))
    async def question(message: Message) -> None:
        await reply(message, message.text)

    return router


async def run_bot(store, cfg: Config) -> None:
    state = State(cfg.state_dir, cfg.history_turns)
    engine = Engine(cfg, Retriever(store), state)
    bot = Bot(cfg.bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(cfg, store, state, engine))
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()
