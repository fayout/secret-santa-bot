import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import BOT_TOKEN, WEBAPP_URL, BOT_USERNAME
import database as db

logger = logging.getLogger(__name__)

bot: Bot | None = None
dp = Dispatcher()

if BOT_TOKEN and BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE" and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
    try:
        bot = Bot(token=BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to initialize Bot with provided token: {e}")
        bot = None

def get_webapp_url(path: str = "") -> str:
    url = WEBAPP_URL.rstrip("/")
    if path:
        return f"{url}/{path.lstrip('/')}"
    return url

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    user = message.from_user
    if not user:
        return

    # Upsert user to database
    await db.upsert_user(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name or "",
        username=user.username or ""
    )

    args = message.text.split(maxsplit=1)
    invite_code = None
    if len(args) > 1:
        param = args[1].strip()
        if param.startswith("room_"):
            invite_code = param[5:]
        elif param.startswith("SANTA-"):
            invite_code = param

    # If invited to a specific room
    if invite_code:
        room = await db.get_room_by_code(invite_code)
        if room:
            room_url = f"{get_webapp_url()}?room={room['code']}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🎁 Войти в комнату «{room['title']}»",
                        web_app=WebAppInfo(url=room_url)
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎄 Главное меню",
                        web_app=WebAppInfo(url=get_webapp_url())
                    )
                ]
            ])
            text = (
                f"👋 Привет, {user.first_name}!\n\n"
                f" тебя пригласили в игру **«Тайный Санта»**!\n"
                f"🏠 Комната: **{room['title']}**\n"
                f"💰 Бюджет: **{room['budget'] or 'Свободный'}**\n\n"
                f"Нажми кнопку ниже, чтобы зайти в комнату, написать своё заветное желание и дождаться жеребьёвки! 🎅"
            )
            await message.answer(text, parse_mode="Markdown", reply_markup=kb)
            return

    # Default start greeting
    main_url = get_webapp_url()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎅 Открыть Тайного Санту",
                web_app=WebAppInfo(url=main_url)
            )
        ],
        [
            InlineKeyboardButton(
                text="➕ Создать комнату",
                web_app=WebAppInfo(url=f"{main_url}?action=create")
            )
        ]
    ])

    text = (
        f"🎅 **Привет, {user.first_name}! Добро пожаловать в Тайного Санту!** 🎄\n\n"
        f"Здесь можно легко организовать обмен новогодними подарками среди друзей или коллег:\n"
        f"• 🏠 Создавай свои комнаты или вступай по ссылке-приглашению\n"
        f"• 🎁 Пиши список подарков (вишлист) и «анти-желания» (что точно не дарить)\n"
        f"• 🔒 Жеребьёвка абсолютно анонимна — никто не знает, кто кому дарит!\n"
        f"• 🛡️ Защита от взаимного дарения и самодарения.\n\n"
        f"Нажми кнопку ниже, чтобы начать! 👇"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.message(Command("myrooms"))
async def handle_my_rooms(message: types.Message):
    user = message.from_user
    if not user:
        return
    rooms = await db.get_user_rooms(user.id)
    if not rooms:
        await message.answer(
            "У тебя пока нет активных комнат. Нажми «Создать комнату», чтобы стать организатором!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать комнату", web_app=WebAppInfo(url=f"{get_webapp_url()}?action=create"))]
            ])
        )
        return

    text = "🎄 **Твои комнаты в Тайном Санте:**\n\n"
    for r in rooms:
        status_emoji = "⏳ В ожидании" if r["status"] == "LOBBY" else "🎉 Игра началась"
        text += f"• **{r['title']}** ({status_emoji})\n  Код: `{r['code']}` | Участников: {r['participants_count']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎅 Открыть приложение", web_app=WebAppInfo(url=get_webapp_url()))]
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def notify_lottery_started(assignments: list):
    """Broadcasts assignments to all participants via Telegram bot."""
    if not bot:
        logger.warning("Bot is not configured, skipping Telegram notifications.")
        return

    for item in assignments:
        santa_id = item["santa_id"]
        receiver_id = item["receiver_id"]
        receiver_name = item["receiver_name"]
        raw_username = (item.get("receiver_username") or "").strip().lstrip("@")
        
        if raw_username:
            profile_url = f"https://t.me/{raw_username}"
            profile_link = f"[@{raw_username}]({profile_url})"
        else:
            profile_url = f"tg://user?id={receiver_id}"
            profile_link = f"[{receiver_name}](tg://user?id={receiver_id})"

        room_title = item["room_title"]
        room_budget = item["room_budget"] or "Свободный"
        wishlist = item["receiver_wishlist"] or "—"
        anti_wishlist = item["receiver_anti_wishlist"] or "Не указано"

        text = (
            f"🎉 **Жеребьёвка в комнате «{room_title}» завершилась!**\n\n"
            f"🎅 **Ты — Тайный Санта для:**\n"
            f"👤 **{receiver_name}** ({profile_link})\n\n"
            f"🎁 **Его/её вишлист (что хочет получить):**\n"
            f"{wishlist}\n\n"
            f"🚫 **Анти-желания (что НЕ дарить):**\n"
            f"{anti_wishlist}\n\n"
            f"💰 **Бюджет комнаты:** {room_budget}\n\n"
            f"🤫 *Никому не раскрывай тайну до самого праздника! Счастливого Нового Года!* 🎄✨"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Открыть в приложении", web_app=WebAppInfo(url=f"{get_webapp_url()}?room_id={item.get('room_id', '')}"))]
        ])


        try:
            await bot.send_message(chat_id=santa_id, text=text, parse_mode="Markdown", reply_markup=kb)
        except TelegramForbiddenError:
            logger.warning(f"User {santa_id} blocked bot or hasn't started it.")
        except Exception as e:
            logger.error(f"Error sending notification to user {santa_id}: {e}")

