import os
import asyncio
import random
import logging
import aiohttp
import sqlite3
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

conn = sqlite3.connect("bot_data.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        rank TEXT DEFAULT 'unverified'
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        used INTEGER DEFAULT 0,
        target_user_id INTEGER
    )
""")
conn.commit()

def get_rank(user_id: int) -> str:
    cursor.execute("SELECT rank FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else "unverified"

def set_rank(user_id: int, username: str, rank: str):
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, rank) VALUES (?, ?, ?)", (user_id, username, rank))
    conn.commit()

def check_rank(required: str):
    ranks = {"unverified": 0, "verified": 1, "owner": 2}
    async def decorator(message: Message):
        user_rank = get_rank(message.from_user.id)
        if ranks.get(user_rank, 0) < ranks.get(required, 0):
            await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
            return False
        return True
    return decorator


@router.message(CommandStart())
async def cmd_start(message: Message):
    set_rank(message.from_user.id, message.from_user.username or "unknown", "unverified")
    await message.answer(
        "Приветствую! Это бот-помощник для верифицированных людей, /guide, "
        "чтобы получить роль \"верифицированный\", /help для полного списка команд."
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    user_rank = get_rank(message.from_user.id)
    text = "📋 <b>Список команд:</b>\n\n"
    text += "👤 <b>Неверифицированный:</b>\n"
    text += "/start - Начать работу\n"
    text += "/help - Список команд\n"
    text += "/questionnaire - Анкета\n"
    text += "/guide - Гайд по верификации\n"
    text += "/activate <текст> - Активировать промокод\n\n"
    if user_rank in ("verified", "owner"):
        text += "💎 <b>Верифицированный:</b>\n"
        text += "/currency - Курс валют\n"
        text += "/calculator <пример> - Калькулятор\n"
        text += "/ai <текст> - ИИ-помощник\n"
        text += "/guide - Гайд\n"
        text += "/verifiedchat - Наш чат\n"
        text += "/questionnaire - Анкета\n"
        text += "/chance <текст или текст> - Случайный выбор\n"
        text += "/cubes @user - Игра в кубики\n\n"
    if user_rank == "owner":
        text += "👑 <b>Управляющий:</b>\n"
        text += "/passcreate <текст> @user - Создать промокод\n"
        text += "/pickup @user - Забрать верификацию\n"
    await message.answer(text)

@router.message(Command("questionnaire"))
async def cmd_questionnaire(message: Message):
    user = message.from_user
    rank = get_rank(user.id)
    rank_names = {"unverified": "Неверифицированный", "verified": "Верифицированный", "owner": "Управляющий"}
    text = (
        "📊 <b>Анкета:</b>\n\n"
        f"👤 Username – @{user.username if user.username else 'не указан'}\n"
        f"🆔 Telegram id – {user.id}\n"
        f"💎 Ранг – {rank_names.get(rank, 'Неверифицированный')}"
    )
    await message.answer(text)

@router.message(Command("guide"))
async def cmd_guide(message: Message):
    text = (
        "✅ <b>Как пройти верификацию:</b>\n\n"
        "1) Зайти в чат https://t.me/LuxoGram_verification.\n\n"
        "2) Написать чем ты занимаешься, например: если ты программист написать "
        "\"Я программист, пишу на языке программирования ..., На библиотеке ..., Мой проект ...\n\n"
        "3) Ждать, если ты подходишь, тебе напишут в лс или в ответ на сообщение."
    )
    await message.answer(text)

@router.message(Command("activate"))
async def cmd_activate(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("Введите промокод: /activate <текст>")
        return
    code = command.args.strip()
    cursor.execute("SELECT used, target_user_id FROM promocodes WHERE code = ?", (code,))
    result = cursor.fetchone()
    if not result:
        await message.answer("❌ Неверный промокод.")
        return
    used, target_user_id = result
    if used:
        await message.answer("❌ Промокод уже использован.")
        return
    if target_user_id and target_user_id != message.from_user.id:
        await message.answer("❌ Этот промокод не для вас.")
        return
    cursor.execute("UPDATE promocodes SET used = 1 WHERE code = ?", (code,))
    set_rank(message.from_user.id, message.from_user.username or "unknown", "verified")
    conn.commit()
    await message.answer("✅ Вы получили ранг «Верифицированный»!")


@router.message(Command("currency"))
async def cmd_currency(message: Message):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.exchangerate-api.com/v4/latest/USD") as r:
                data = await r.json()
            rates = data.get("rates", {})
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,dogecoin&vs_currencies=usd") as r:
                crypto = await r.json()
        text = "💱 <b>Курс валют (USD):</b>\n\n"
        text += f"🇷🇺 Рубль: {rates.get('RUB', 'N/A')}₽\n"
        text += f"🇺🇸 Доллар: 1$\n"
        text += f"🇪🇺 Евро: {rates.get('EUR', 'N/A')}€\n"
        text += f"🇨🇳 Юань: {rates.get('CNY', 'N/A')}¥\n"
        text += f"🇧🇾 Бел. рубль: {rates.get('BYN', 'N/A')} Br\n"
        text += f"🇬🇧 Фунт: £{rates.get('GBP', 'N/A')}\n\n"
        text += "🪙 <b>Криптовалюты (USD):</b>\n\n"
        text += f"₿ Bitcoin: ${crypto.get('bitcoin', {}).get('usd', 'N/A')}\n"
        text += f"Ξ Ethereum: ${crypto.get('ethereum', {}).get('usd', 'N/A')}\n"
        text += f"◎ Solana: ${crypto.get('solana', {}).get('usd', 'N/A')}\n"
        text += f"🐕 Dogecoin: ${crypto.get('dogecoin', {}).get('usd', 'N/A')}"
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Ошибка получения курса: {e}")

@router.message(Command("calculator"))
async def cmd_calculator(message: Message, command: CommandObject):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    if not command.args:
        await message.answer("Введите пример: /calculator 2+2*2")
        return
    try:
        result = eval(command.args)
        await message.answer(f"🔢 <b>Результат:</b> {result}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("ai"))
async def cmd_ai(message: Message, command: CommandObject):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    if not command.args:
        await message.answer("Введите текст: /ai <текст>")
        return
    user_text = command.args
    await message.answer("🤖 Думаю...")
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [{"role": "user", "content": user_text}]
            }
            async with session.post(url, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    data = await r.json()
                    response = data["choices"][0]["message"]["content"]
                    await message.answer(f"🤖 <b>Ответ ИИ:</b>\n\n{response}")
                    return
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": user_text}]
            }
            async with session.post(url, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    data = await r.json()
                    response = data["choices"][0]["message"]["content"]
                    await message.answer(f"🤖 <b>Ответ ИИ:</b>\n\n{response}")
                else:
                    await message.answer("❌ ИИ недоступен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка ИИ: {e}")

@router.message(Command("verifiedchat"))
async def cmd_verifiedchat(message: Message):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    await message.answer("✅ Наш чат – https://t.me/LuxoGramTalk.")

@router.message(Command("chance"))
async def cmd_chance(message: Message, command: CommandObject):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    if not command.args or " или " not in command.args:
        await message.answer("Введите: /chance вариант1 или вариант2")
        return
    parts = command.args.split(" или ", 1)
    choice = random.choice([p.strip() for p in parts])
    await message.answer(f"🎲 <b>Выбор сделан:</b>\n\n{choice}")

cubes_data = {}

@router.message(Command("cubes"))
async def cmd_cubes(message: Message, command: CommandObject):
    if get_rank(message.from_user.id) not in ("verified", "owner"):
        await message.answer("Вы не можете выполнить эту команду, так как у вас нет нужного ранга.")
        return
    if not command.args:
        await message.answer("Укажите юзернейм: /cubes @username")
        return
    target = command.args.strip().replace("@", "")
    target_user = None
    async for member in message.bot.get_chat_administrators(message.chat.id) if message.chat.type != "private" else []:
        if member.user.username and member.user.username.lower() == target.lower():
            target_user = member.user
            break
    if not target_user:
        await message.answer("❌ Пользователь не найден в этом чате. Добавьте его в чат и попробуйте снова, или введите правильный @username.")
        return
    inviter = message.from_user
    cubes_data[target_user.id] = {"inviter": inviter, "target": target_user}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"cubes_accept:{target_user.id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"cubes_decline:{target_user.id}")
        ]
    ])
    await message.answer(
        f"@{target_user.username} минуточку внимания!\n"
        f"@{inviter.username} предлагает вам бросить кубики.",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("cubes_accept:"))
async def cubes_accept(callback: CallbackQuery):
    target_user_id = int(callback.data.split(":")[1])
    data = cubes_data.get(target_user_id)
    if not data:
        await callback.answer("❌ Игра не найдена.")
        return
    inviter = data["inviter"]
    target = data["target"]
    if callback.from_user.id != target_user_id:
        await callback.answer("❌ Это не ваша игра.")
        return
    roll1 = random.randint(1, 6)
    await callback.message.answer(f"Первый бросок кубика совершает @{target.username}\n🎲 {roll1}")
    await asyncio.sleep(1)
    roll2 = random.randint(1, 6)
    await callback.message.answer(f"Второй бросок кубика совершает @{inviter.username}\n🎲 {roll2}")
    await asyncio.sleep(1)
    if roll1 > roll2:
        winner, loser = target, inviter
    elif roll2 > roll1:
        winner, loser = inviter, target
    else:
        await callback.message.answer("🤝 Ничья! Кубики равны.")
        del cubes_data[target_user_id]
        return
    await callback.message.answer(
        f"Игроки бросили кубики.\n"
        f"👑 Победитель – @{winner.username}\n"
        f"✖ Проигравший – @{loser.username}"
    )
    del cubes_data[target_user_id]

@router.callback_query(F.data.startswith("cubes_decline:"))
async def cubes_decline(callback: CallbackQuery):
    target_user_id = int(callback.data.split(":")[1])
    data = cubes_data.get(target_user_id)
    if not data:
        await callback.answer("❌ Игра не найдена.")
        return
    inviter = data["inviter"]
    target = data["target"]
    if callback.from_user.id != target_user_id:
        await callback.answer("❌ Это не ваша игра.")
        return
    await callback.message.answer(
        f"@{inviter.username} минуточку внимания! "
        f"@{target.username} отказался бросить кубики."
    )
    del cubes_data[target_user_id]


@router.message(Command("passcreate"))
async def cmd_passcreate(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        return
    if not command.args:
        await message.answer("Использование: /passcreate <промокод> @username")
        return
    args = command.args
    if " " not in args:
        await message.answer("Укажите промокод и @username")
        return
    parts = args.rsplit(" ", 1)
    code = parts[0].strip()
    target_username = parts[1].strip().replace("@", "")
    cursor.execute("SELECT user_id FROM users WHERE username = ?", (target_username,))
    result = cursor.fetchone()
    if not result:
        await message.answer("❌ Пользователь не найден. Он должен сначала написать /start боту.")
        return
    target_user_id = result[0]
    try:
        cursor.execute("INSERT INTO promocodes (code, used, target_user_id) VALUES (?, 0, ?)", (code, target_user_id))
        conn.commit()
        await message.answer(f"✅ Промокод <code>{code}</code> создан для @{target_username}")
    except sqlite3.IntegrityError:
        await message.answer("❌ Такой промокод уже существует.")

@router.message(Command("pickup"))
async def cmd_pickup(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        return
    if not command.args:
        await message.answer("Использование: /pickup @username")
        return
    target_username = command.args.strip().replace("@", "")
    cursor.execute("UPDATE users SET rank = 'unverified' WHERE username = ?", (target_username,))
    if cursor.rowcount > 0:
        conn.commit()
        await message.answer(f"✅ У @{target_username} забрана верификация.")
    else:
        await message.answer("❌ Пользователь не найден.")


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
