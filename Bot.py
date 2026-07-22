import asyncio
import json
import os
import random
import ast
import operator
from pathlib import Path
from typing import Optional
import urllib.parse

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-4o-mini")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
CODES_FILE = DATA_DIR / "codes.json"

RANK_UNVERIFIED = "unverified"
RANK_VERIFIED = "verified"
RANK_OWNER = "owner"

RANK_NAMES = {
    RANK_UNVERIFIED: "Неверифицированный",
    RANK_VERIFIED: "Верифицированный",
    RANK_OWNER: "Управляющий",
}

NO_RIGHTS_TEXT = "Вы не можете выполнить эту команду, так как у вас нет нужного ранга."

storage_lock = asyncio.Lock()


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def get_users() -> dict:
    async with storage_lock:
        return _read_json(USERS_FILE)


async def save_users(data: dict) -> None:
    async with storage_lock:
        _write_json(USERS_FILE, data)


async def get_codes() -> dict:
    async with storage_lock:
        return _read_json(CODES_FILE)


async def save_codes(data: dict) -> None:
    async with storage_lock:
        _write_json(CODES_FILE, data)


async def ensure_user(user_id: int, username: Optional[str]) -> dict:
    users = await get_users()
    uid = str(user_id)
    username = username or ""
    if uid not in users:
        users[uid] = {"username": username, "rank": RANK_UNVERIFIED}
        await save_users(users)
    elif users[uid].get("username") != username:
        users[uid]["username"] = username
        await save_users(users)
    return users[uid]


async def get_rank(user_id: int) -> str:
    if user_id == OWNER_ID:
        return RANK_OWNER
    users = await get_users()
    uid = str(user_id)
    if uid not in users:
        return RANK_UNVERIFIED
    return users[uid].get("rank", RANK_UNVERIFIED)


async def set_rank(user_id: int, rank: str) -> None:
    users = await get_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"username": "", "rank": rank}
    else:
        users[uid]["rank"] = rank
    await save_users(users)


async def find_user_by_username(username: str) -> Optional[tuple]:
    username = username.lstrip("@").lower()
    users = await get_users()
    for uid, info in users.items():
        if info.get("username", "").lower() == username:
            return uid, info
    return None


router = Router()

HELP_TEXT = (
    "📋 Список команд:\n\n"
    "🔹 Неверифицированный:\n"
    "/start – запустить бота\n"
    "/help – список команд\n"
    "/questionnaire – анкета пользователя\n"
    "/guide – как пройти верификацию\n"
    "/activate текст – активировать промокод\n\n"
    "🔹 Верифицированный:\n"
    "/start – запустить бота\n"
    "/help – список команд\n"
    "/activate текст – активировать промокод\n"
    "/currency – курс валют\n"
    "/calculator пример – калькулятор\n"
    "/ai текст – спросить ИИ\n"
    "/guide – как пройти верификацию\n"
    "/verifiedchat – ссылка на чат\n"
    "/questionnaire – анкета пользователя\n"
    "/chance текст или текст – рандомный выбор\n"
    "/cubes @юз – бросить кубики\n"
    "/search текст – поиск в Яндексе\n\n"
    "🔹 Управляющий:\n"
    "/passcreate текст @юз – создать промокод\n"
    "/pickup @юз – забрать верификацию\n\n"
    "🔹 Для всех:\n"
    "/botinfo – информация о боте\n"
)

GUIDE_TEXT = (
    "✅ Как пройти верификацию:\n\n"
    "1) Зайти в чат https://t.me/LuxoGram_verification.\n\n"
    "2) Написать чем ты занимаешься, например: если ты программист написать "
    "\"Я программист, пишу на языке программирования ... , На библиотеке ... , Мой проект ...\"\n\n"
    "3) Ждать, если ты подходишь, тебе напишут в лс или в ответ на сообщение."
)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋Приветствую! Это бот-помощник для верифицированных людей, /guide, "
        "чтобы получить роль \"верифицированный\", /help для полного списка команд."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(HELP_TEXT)


@router.message(Command("questionnaire"))
async def cmd_questionnaire(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    rank = await get_rank(message.from_user.id)
    username = message.from_user.username or "—"
    await message.answer(
        "📊 Анкета:\n"
        f"👤 Username – @{username}\n"
        f"🆔 Telegram id – {message.from_user.id}\n"
        f"💎 Ранг – {RANK_NAMES[rank]}"
    )


@router.message(Command("guide"))
async def cmd_guide(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(GUIDE_TEXT, disable_web_page_preview=True)


@router.message(Command("activate"))
async def cmd_activate(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите промокод: /activate текст")
        return
    code = parts[1].strip()
    codes = await get_codes()
    entry = codes.get(code)
    if not entry or entry.get("used"):
        await message.answer("❌ Промокод недействителен.")
        return
    allowed_username = entry.get("username", "").lstrip("@").lower()
    user_username = (message.from_user.username or "").lower()
    if allowed_username and allowed_username != user_username:
        await message.answer("❌ Промокод недействителен.")
        return
    entry["used"] = True
    codes[code] = entry
    await save_codes(codes)
    await set_rank(message.from_user.id, RANK_VERIFIED)
    await message.answer("✅ Промокод активирован! Вам выдана роль \"Верифицированный\".")


FIAT_SYMBOLS = {
    "RUB": "🇷🇺 Рубль",
    "USD": "🇺🇸 Доллар",
    "EUR": "🇪🇺 Евро",
    "CNY": "🇨🇳 Юань",
    "BYN": "🇧🇾 Белорусский рубль",
    "GBP": "🇬🇧 Фунт",
}

CRYPTO_IDS = {
    "bitcoin": "Биткоин",
    "ethereum": "ETH",
    "solana": "SOLARA",
    "dogecoin": "DOGE",
}


@router.message(Command("currency"))
async def cmd_currency(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    lines = ["💱 Курс валют к доллару (USD):\n"]
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                fiat_data = await resp.json()
            rates = fiat_data.get("rates", {})
            for code, label in FIAT_SYMBOLS.items():
                rate = rates.get(code)
                if rate:
                    lines.append(f"{label}: {rate:.2f}")
        except Exception:
            lines.append("Не удалось получить курсы фиатных валют.")

        try:
            ids = ",".join(CRYPTO_IDS.keys())
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                crypto_data = await resp.json()
            lines.append("")
            for cid, label in CRYPTO_IDS.items():
                price = crypto_data.get(cid, {}).get("usd")
                if price:
                    lines.append(f"{label}: {price:,.2f} $")
        except Exception:
            lines.append("Не удалось получить курсы криптовалют.")

    await message.answer("\n".join(lines))


ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Недопустимое значение")
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
        return ALLOWED_OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_OPERATORS:
        return ALLOWED_OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Недопустимое выражение")


def safe_eval(expr: str):
    node = ast.parse(expr, mode="eval").body
    return _eval_node(node)


@router.message(Command("calculator"))
async def cmd_calculator(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите пример: /calculator 2+2*2")
        return
    try:
        result = safe_eval(parts[1].strip())
        await message.answer(f"🧮 Результат: {result}")
    except Exception:
        await message.answer("❌ Не удалось решить пример. Проверьте выражение.")


async def _ask_openrouter(prompt: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}]}
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception:
        return None


async def _ask_groq(prompt: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}]}
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception:
        return None


@router.message(Command("ai"))
async def cmd_ai(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите текст запроса: /ai текст")
        return
    prompt = parts[1].strip()
    await message.bot.send_chat_action(message.chat.id, "typing")

    answer = None
    if OPENROUTER_API_KEY:
        answer = await _ask_openrouter(prompt)
    if answer is None and GROQ_API_KEY:
        answer = await _ask_groq(prompt)

    if answer is None:
        await message.answer("❌ Не удалось получить ответ от ИИ.")
    else:
        await message.answer(answer)


@router.message(Command("verifiedchat"))
async def cmd_verifiedchat(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return
    await message.answer("✅ Наш чат – https://t.me/LuxoGramTalk.", disable_web_page_preview=True)


@router.message(Command("chance"))
async def cmd_chance(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите варианты: /chance месси или роналдо")
        return
    text = parts[1].strip()
    if " или " in text:
        options = [opt.strip() for opt in text.split(" или ") if opt.strip()]
    else:
        options = [opt.strip() for opt in text.split() if opt.strip()]
    if len(options) < 2:
        await message.answer("Укажите минимум два варианта через \"или\".")
        return
    await message.answer(f"🎯 Выбор: {random.choice(options)}")


active_dice_games: dict = {}


@router.message(Command("cubes"))
async def cmd_cubes(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().startswith("@"):
        await message.answer("Укажите пользователя: /cubes @username")
        return
    target_username = parts[1].strip().lstrip("@")
    initiator_username = message.from_user.username or str(message.from_user.id)

    if target_username.lower() == initiator_username.lower():
        await message.answer("❌ Нельзя предложить кубики самому себе.")
        return

    game_id = f"{message.chat.id}_{message.message_id}"
    active_dice_games[game_id] = {
        "initiator_username": initiator_username,
        "target_username": target_username,
    }

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять", callback_data=f"cubes_accept:{game_id}")
    builder.button(text="❌ Отказать", callback_data=f"cubes_decline:{game_id}")

    await message.answer(
        f"@{target_username} минуточку внимания!\n"
        f"@{initiator_username} предлагает вам бросить кубики.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("cubes_decline:"))
async def cb_cubes_decline(callback: CallbackQuery):
    game_id = callback.data.split(":", 1)[1]
    game = active_dice_games.get(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    responder_username = callback.from_user.username or ""
    if responder_username.lower() != game["target_username"].lower():
        await callback.answer("Это предложение не для вас.", show_alert=True)
        return

    await callback.message.edit_text(
        f"@{game['initiator_username']} минуточку внимания! "
        f"@{game['target_username']} отказался бросить кубики."
    )
    active_dice_games.pop(game_id, None)
    await callback.answer()


@router.callback_query(F.data.startswith("cubes_accept:"))
async def cb_cubes_accept(callback: CallbackQuery):
    game_id = callback.data.split(":", 1)[1]
    game = active_dice_games.get(game_id)
    if not game:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    responder_username = callback.from_user.username or ""
    if responder_username.lower() != game["target_username"].lower():
        await callback.answer("Это предложение не для вас.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    target_username = game["target_username"]
    initiator_username = game["initiator_username"]

    await callback.message.answer(f"Первый бросок кубика совершает @{target_username}.")
    first_roll = random.randint(1, 6)
    await callback.message.answer(f"🎲 {first_roll}")

    await callback.message.answer(f"Второй бросок кубика совершает @{initiator_username}.")
    second_roll = random.randint(1, 6)
    await callback.message.answer(f"🎲 {second_roll}")

    if first_roll == second_roll:
        await callback.message.answer(f"Игроки бросили кубики.\nНичья! Оба выбросили {first_roll}.")
    else:
        if first_roll > second_roll:
            winner, loser = target_username, initiator_username
        else:
            winner, loser = initiator_username, target_username
        await callback.message.answer(
            "Игроки бросили кубики.\n"
            f"👑 Победитель – @{winner}\n"
            f"✖ Проигравший – @{loser}"
        )

    active_dice_games.pop(game_id, None)


@router.message(Command("passcreate"))
async def cmd_passcreate(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[2].strip().startswith("@"):
        await message.answer("Использование: /passcreate текст @username")
        return
    code = parts[1]
    username = parts[2].strip().lstrip("@")
    codes = await get_codes()
    codes[code] = {"username": username, "used": False}
    await save_codes(codes)
    await message.answer(f"✅ Промокод \"{code}\" создан для @{username}.")


@router.message(Command("pickup"))
async def cmd_pickup(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().startswith("@"):
        await message.answer("Использование: /pickup @username")
        return
    username = parts[1].strip().lstrip("@")
    found = await find_user_by_username(username)
    if not found:
        await message.answer("❌ Пользователь не найден.")
        return
    uid, _info = found
    await set_rank(int(uid), RANK_UNVERIFIED)
    await message.answer(f"✅ У @{username} забрана верификация.")


@router.message(Command("search"))
async def cmd_search(message: Message):
    rank = await get_rank(message.from_user.id)
    if rank not in (RANK_VERIFIED, RANK_OWNER):
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите текст для поиска: /search ваш запрос")
        return

    query = parts[1].strip()
    encoded_query = urllib.parse.quote(query)
    yandex_url = f"https://yandex.ru/search/?text={encoded_query}"
    await message.answer(f"🔍 Поиск в Яндексе:\n{yandex_url}", disable_web_page_preview=True)


@router.message(Command("botinfo"))
async def cmd_botinfo(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username)
    info_text = (
        "Информация о боте:\n"
        "📄Язык программирования: Python.\n"
        "📚Библиотека: Aiogram.\n"
        "👨‍💻Кодер: @Luxscer.\n"
        "📊Стадия в разработке: Beta."
    )
    await message.answer(info_text)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения.")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
