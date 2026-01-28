import asyncio
import random
import sqlite3
import os
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

BOT_TOKEN = "8467966817:AAH_iPRb89HrujtrveTsHfdsZ2zAHZleM5A"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class CreateGiveaway(StatesGroup):
    waiting_for_text = State()
    waiting_for_button = State()
    waiting_for_channels = State()
    waiting_for_winners = State()
    waiting_for_channel = State()
    waiting_for_publish_time = State()
    waiting_for_end_type = State()
    waiting_for_end_time = State()
    waiting_for_end_count = State()

class AddChannel(StatesGroup):
    waiting_for_channel = State()

def init_database():
    conn = sqlite3.connect("giveaways.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel_id TEXT,
        channel_username TEXT,
        channel_name TEXT,
        UNIQUE(user_id, channel_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        media_type TEXT,
        media_file_id TEXT,
        button_text TEXT,
        channels TEXT,
        winners_count INTEGER,
        channel_id TEXT,
        publish_time TEXT,
        end_type TEXT,
        end_time TEXT,
        end_count INTEGER,
        participants TEXT DEFAULT '[]',
        created_at TEXT,
        is_published BOOLEAN DEFAULT FALSE,
        check_code TEXT
    )
    """)

    conn.commit()
    return conn, cursor

def update_database_structure():
    cursor.execute("PRAGMA table_info(giveaways)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'check_code' not in columns:
        cursor.execute("ALTER TABLE giveaways ADD COLUMN check_code TEXT")
        conn.commit()

conn, cursor = init_database()
update_database_structure()

async def setup_commands(bot):
    from aiogram.types import BotCommand, BotCommandScopeDefault
    commands = [
        BotCommand(command="/start", description="Начать работу"),
        BotCommand(command="/new_lot", description="Создать розыгрыш"),
        BotCommand(command="/my_lots", description="Мои розыгрыши"),
        BotCommand(command="/my_channels", description="Мои каналы"),
        BotCommand(command="/delete_channel", description="Удалить канал"),
        BotCommand(command="/support", description="Техническая поддержка"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎁 Создать розыгрыш")],
            [KeyboardButton(text="📋 Мои розыгрыши"), KeyboardButton(text="📢 Мои каналы")],
            [KeyboardButton(text="🛠️ Техническая поддержка")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def generate_check_code(giveaway_id: int, user_id: int) -> str:
    import hashlib
    import time
    secret = f"{giveaway_id}_{user_id}_{time.time()}"
    return hashlib.md5(secret.encode()).hexdigest()

async def is_bot_admin_in_channel(channel_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

async def check_user_subscription(user_id: int, channels: list) -> bool:
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True

def add_participant(giveaway_id: int, user_id: int):
    cursor.execute("SELECT participants FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if row:
        participants = eval(row[0])
        if user_id not in participants:
            participants.append(user_id)
            cursor.execute("UPDATE giveaways SET participants = ? WHERE id = ?", (str(participants), giveaway_id))
            conn.commit()

def get_participants_count(giveaway_id: int) -> int:
    cursor.execute("SELECT participants FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if row and row[0]:
        participants = eval(row[0])
        return len(participants)
    return 0

async def publish_giveaway_to_channel(giveaway_id: int):
    cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if not row:
        return False

    cursor.execute("PRAGMA table_info(giveaways)")
    columns = [column[1] for column in cursor.fetchall()]
    num_columns = len(columns)
    
    data_dict = dict(zip(columns, row))
    
    if data_dict.get('is_published'):
        return True

    participants_count = get_participants_count(giveaway_id)
    button_text = data_dict.get('button_text', 'Участвовать')
    button_text_with_count = f"{button_text} ({participants_count})"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text_with_count, callback_data=f"participate_{giveaway_id}")]
    ])

    try:
        text = data_dict.get('text', '')
        media_type = data_dict.get('media_type')
        media_file_id = data_dict.get('media_file_id')
        channel_id = data_dict.get('channel_id')

        if media_type and media_file_id:
            if media_type == "photo":
                message = await bot.send_photo(
                    chat_id=channel_id,
                    photo=media_file_id,
                    caption=text,
                    reply_markup=keyboard
                )
            elif media_type == "video":
                message = await bot.send_video(
                    chat_id=channel_id,
                    video=media_file_id,
                    caption=text,
                    reply_markup=keyboard
                )
            elif media_type == "gif":
                message = await bot.send_animation(
                    chat_id=channel_id,
                    animation=media_file_id,
                    caption=text,
                    reply_markup=keyboard
                )
        else:
            message = await bot.send_message(
                chat_id=channel_id,
                text=text,
                reply_markup=keyboard
            )
        
        cursor.execute("UPDATE giveaways SET is_published = TRUE WHERE id = ?", (giveaway_id,))
        conn.commit()
        
        return True
    except Exception as e:
        print(f"Ошибка при публикации розыгрыша: {e}")
        return False

async def update_giveaway_button(giveaway_id: int, channel_id: str, message_id: int):
    cursor.execute("SELECT button_text FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if not row:
        return
    
    button_text = row[0]
    participants_count = get_participants_count(giveaway_id)
    button_text_with_count = f"{button_text} ({participants_count})"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text_with_count, callback_data=f"participate_{giveaway_id}")]
    ])
    
    try:
        await bot.edit_message_reply_markup(
            chat_id=channel_id,
            message_id=message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка при обновлении кнопки: {e}")

async def finish_giveaway_job(giveaway_id: int):
    cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if not row:
        return

    cursor.execute("PRAGMA table_info(giveaways)")
    columns = [column[1] for column in cursor.fetchall()]
    data_dict = dict(zip(columns, row))
    
    participants_str = data_dict.get('participants', '[]')
    participants = eval(participants_str) if participants_str else []
    winners_count = data_dict.get('winners_count', 1)
    channel_id = data_dict.get('channel_id')

    if not participants:
        result_text = "❌ Розыгрыш завершен. Никто не участвовал."
    else:
        winners = random.sample(participants, min(len(participants), winners_count))
        result_text = "🎉 Результаты розыгрыша:\n🏆 Победитель:\n"
        for i, uid in enumerate(winners, 1):
            try:
                user = await bot.get_chat(uid)
                username = user.username or user.first_name
                result_text += f"{i}. {username} (@{user.username or 'N/A'})\n"
            except Exception:
                result_text += f"{i}. Пользователь {uid}\n"
        
        check_url = f"http://t.me/Random1zeBot?start=checklot{giveaway_id}{generate_check_code(giveaway_id, 0)}"
        result_text += f"\n✔️Проверить результаты ({check_url})"

    try:
        await bot.send_message(chat_id=channel_id, text=result_text)
        cursor.execute("SELECT user_id FROM channels WHERE channel_username = ?", (channel_id,))
        creator_row = cursor.fetchone()
        if creator_row:
            await bot.send_message(chat_id=creator_row[0], text=result_text)
    except Exception as e:
        print(f"Ошибка при отправке результата: {e}")

@dp.callback_query(F.data.startswith("participate_"))
async def participate_in_giveaway(call: CallbackQuery):
    giveaway_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    
    if call.from_user.is_bot:
        await call.answer("❌ Боты не могут участвовать в розыгрышах!", show_alert=True)
        return
    
    cursor.execute("SELECT channels FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if not row:
        await call.answer("❌ Розыгрыш не найден!", show_alert=True)
        return
    
    channels_str = row[0]
    channels = channels_str.split(',') if channels_str else []
    
    is_subscribed = await check_user_subscription(user_id, channels)
    if not is_subscribed:
        await call.answer("❌ Вы не подписаны на все необходимые каналы!", show_alert=True)
        return
    
    cursor.execute("SELECT participants FROM giveaways WHERE id = ?", (giveaway_id,))
    row = cursor.fetchone()
    if row and row[0]:
        participants = eval(row[0])
        if user_id in participants:
            await call.answer("✅ Вы уже участвуете в этом розыгрыше!", show_alert=True)
            return
    
    add_participant(giveaway_id, user_id)
    await call.answer("✅ Вы успешно приняли участие в розыгрыше!", show_alert=True)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = get_main_keyboard()
    await message.answer(
        "Приветствуем!\n"
        "Наш бот поможет Вам провести розыгрыш в канале или чате.\n"
        "Готовы создать новый розыгрыш?",
        reply_markup=keyboard
    )

@dp.message(Command("support"))
async def cmd_support(message: Message):
    await message.answer(
        "🛠️ Техническая поддержка\n\n"
        "Если у вас возникли проблемы с работой бота или есть вопросы:\n\n"
        "📧 Напишите нам: @carniz_support\n"
        "⏰ Время работы: 24/7\n"
        "🚀 Мы всегда готовы помочь!"
    )

@dp.message(F.text == "🎁 Создать розыгрыш")
async def create_giveaway_button(message: Message, state: FSMContext):
    await cmd_new_lot(message, state)

@dp.message(F.text == "📋 Мои розыгрыши")
async def my_giveaways_button(message: Message):
    await cmd_my_lots(message)

@dp.message(F.text == "📢 Мои каналы")
async def my_channels_button(message: Message):
    await cmd_my_channels(message)

@dp.message(F.text == "🛠️ Техническая поддержка")
async def support_button(message: Message):
    await cmd_support(message)

@dp.message(Command("new_lot"))
async def cmd_new_lot(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT channel_name, channel_username FROM channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("❌ Сначала добавьте канал в разделе 'Мои каналы'.")
        return
    
    await message.answer(
        "✉️ Отправьте текст для розыгрыша. Вы можете также отправить вместе с текстом 🖼 картинку, видео, GIF или Премиум🎆эмодзи, а так же пользоваться разметкой.\n"
        "❗️ Вы можете использовать только 1 медиафайл."
    )
    await state.set_state(CreateGiveaway.waiting_for_text)

@dp.callback_query(F.data == "create_giveaway")
async def create_giveaway_start(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    cursor.execute("SELECT channel_name, channel_username FROM channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await call.message.answer("❌ Сначала добавьте канал в разделе 'Мои каналы'.")
        return
    
    await call.message.answer(
        "✉️ Отправьте текст для розыгрыша. Вы можете также отправить вместе с текстом 🖼 картинку, видео, GIF или Премиум🎆эмодзи, а так же пользоваться разметкой.\n"
        "❗️ Вы можете использовать только 1 медиафайл."
    )
    await state.set_state(CreateGiveaway.waiting_for_text)
    await call.answer()

@dp.message(CreateGiveaway.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    media_type = None
    media_file_id = None

    if message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    elif message.animation:
        media_type = "gif"
        media_file_id = message.animation.file_id

    await state.update_data(text=text, media_type=media_type, media_file_id=media_file_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Участвовать", callback_data="btn_join")],
        [InlineKeyboardButton(text="Вступить в розыгрыш", callback_data="btn_enter")],
        [InlineKeyboardButton(text="Принять участие", callback_data="btn_participate")]
    ])
    await message.answer(
        "Отправьте текст, который будет отображаться на кнопке, или выберите один из вариантов кнопкой:",
        reply_markup=keyboard
    )
    await state.set_state(CreateGiveaway.waiting_for_button)

@dp.callback_query(F.data.startswith("btn_"))
async def process_button(call: CallbackQuery, state: FSMContext):
    btn_map = {
        "btn_join": "Участвовать",
        "btn_enter": "Вступить в розыгрыш",
        "btn_participate": "Принять участие"
    }
    button_text = btn_map[call.data]
    await state.update_data(button_text=button_text)
    
    await call.message.edit_text(f"✅ Текст кнопки сохранен: {button_text}")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Розыгрыш без обязательных подписок", callback_data="no_channels")]
    ])
    
    await call.message.answer(
        "Добавьте каналы, на которые пользователям нужно будет подписаться для участия в розыгрыше.\n"
        "❗️Подписка на канал, в котором проводится розыгрыш, обязательна и включена по умолчанию.\n"
        "Чтобы добавить канал, нужно:\n"
        "1. Добавить бота @carniz_bot в этот канал как администратора - это нужно, чтобы бот мог проверить подписан ли пользователь на канал.\n"
        "2. Отправить боту канал в формате ссылки или переслать сообщение из этого канала.\n"
        "💬 Если Вы хотите чтобы участвовать в розыгрыше можно было без подписок на другие каналы, нажмите кнопку ниже:",
        reply_markup=keyboard
    )
    await state.set_state(CreateGiveaway.waiting_for_channels)
    await call.answer()

@dp.callback_query(F.data == "no_channels")
async def no_channels(call: CallbackQuery, state: FSMContext):
    await state.update_data(channels=[])
    await call.message.edit_text("✅ Сохранено: розыгрыш без обязательных подписок")
    await call.message.answer("Сколько победителей выбрать боту?")
    await state.set_state(CreateGiveaway.waiting_for_winners)
    await call.answer()

@dp.message(CreateGiveaway.waiting_for_channels)
async def process_channels(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "нет":
        channels = []
    else:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        channels = []
        for line in lines:
            if line.startswith("https://t.me/"):
                username = line.split("/")[-1]
                channels.append(f"@{username}")
            elif line.startswith("@"):
                channels.append(line)
            else:
                await message.answer(f"❌ Неверный формат ссылки: {line}. Используйте https://t.me/username или @username.")
                return
    
    await state.update_data(channels=channels)
    await message.answer(f"✅ Сохранено каналов: {len(channels)}")
    await message.answer("Сколько победителей выбрать боту?")
    await state.set_state(CreateGiveaway.waiting_for_winners)

@dp.message(CreateGiveaway.waiting_for_winners)
async def process_winners(message: Message, state: FSMContext):
    try:
        winners = int(message.text)
        if winners <= 0:
            await message.answer("❌ Число победителей должно быть больше 0.")
            return
        await state.update_data(winners_count=winners)
        await message.answer(f"✅ Количество победителей сохранено: {winners}")
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    user_id = message.from_user.id
    cursor.execute("SELECT channel_name, channel_username FROM channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    channels = [(row[0], row[1]) for row in rows]

    if not channels:
        await message.answer("❌ У вас нет добавленных каналов. Сначала добавьте канал в разделе 'Мои каналы'.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel_name, callback_data=f"channel_{channel_username}")] 
        for channel_name, channel_username in channels
    ])
    await message.answer("🗒 В каком канале публикуем розыгрыш?", reply_markup=keyboard)
    await state.set_state(CreateGiveaway.waiting_for_channel)

@dp.callback_query(F.data.startswith("channel_"))
async def select_channel(call: CallbackQuery, state: FSMContext):
    channel_username = call.data.split("channel_", 1)[1]
    
    cursor.execute("SELECT channel_name FROM channels WHERE channel_username = ?", (channel_username,))
    row = cursor.fetchone()
    channel_name = row[0] if row else channel_username
    
    await state.update_data(channel_id=channel_username)
    await call.message.edit_text(f"✅ Канал выбран: {channel_name}")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Прямо сейчас", callback_data="publish_now")],
        [InlineKeyboardButton(text="Запланировать публикацию", callback_data="publish_later")]
    ])
    await call.message.answer(
        "⏳ Когда нужно опубликовать розыгрыш? (Укажите время в формате дд.мм.гг чч:мм)\n"
        "Бот живет по времени (GMT+3) Москва, Россия.",
        reply_markup=keyboard
    )
    await state.set_state(CreateGiveaway.waiting_for_publish_time)
    await call.answer()

@dp.callback_query(F.data == "publish_now")
async def publish_now(call: CallbackQuery, state: FSMContext):
    await state.update_data(publish_time="сейчас")
    await call.message.edit_text("✅ Время публикации выбрано: прямо сейчас")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="По времени", callback_data="end_time")],
        [InlineKeyboardButton(text="По кол-ву участников", callback_data="end_count")]
    ])
    await call.message.answer("✍️ Как завершить розыгрыш?", reply_markup=keyboard)
    await state.set_state(CreateGiveaway.waiting_for_end_type)
    await call.answer()

@dp.callback_query(F.data == "publish_later")
async def publish_later(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите время публикации в формате дд.мм.гг чч:мм")
    await state.set_state(CreateGiveaway.waiting_for_publish_time)
    await call.answer()

@dp.message(CreateGiveaway.waiting_for_publish_time)
async def process_publish_time(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        if dt <= datetime.now():
            await message.answer("❌ Время публикации должно быть в будущем.")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте формат: дд.мм.гг чч:мм")
        return
    
    await state.update_data(publish_time=text)
    await message.answer("✅ Время публикации выбрано.")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="По времени", callback_data="end_time")],
        [InlineKeyboardButton(text="По кол-ву участников", callback_data="end_count")]
    ])
    await message.answer("✍️ Как завершить розыгрыш?", reply_markup=keyboard)
    await state.set_state(CreateGiveaway.waiting_for_end_type)

@dp.callback_query(F.data.startswith("end_"))
async def process_end_type(call: CallbackQuery, state: FSMContext):
    if call.data == "end_time":
        now = datetime.now()
        examples = [
            (now + timedelta(minutes=10), "через 10 минут"),
            (now + timedelta(hours=1), "через 1 час"),
            (now + timedelta(days=1), "через 1 день"),
            (now + timedelta(weeks=1), "через 1 неделю")
        ]
        example_text = "\n".join([f"{dt.strftime('%d.%m.%Y %H:%M')} - {desc}" for dt, desc in examples])
        
        await call.message.edit_text(
            f"🔚 Когда нужно определить победителя?\n"
            f"Укажите время в формате дд.мм.гг чч:мм.\n\n"
            f"Примеры:\n{example_text}"
        )
        await state.set_state(CreateGiveaway.waiting_for_end_time)
    elif call.data == "end_count":
        await call.message.edit_text("Введите количество участников для завершения:")
        await state.set_state(CreateGiveaway.waiting_for_end_count)
    
    await call.answer()

@dp.message(CreateGiveaway.waiting_for_end_time)
async def process_end_time(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        if dt <= datetime.now():
            await message.answer("❌ Время завершения должно быть в будущем.")
            return
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте формат: дд.мм.гг чч:мм")
        return
    
    await state.update_data(end_time=text, end_type="time")
    await message.answer("✅ Время для подведения результатов сохранено.")
    await finish_giveaway_creation(message, state)

@dp.message(CreateGiveaway.waiting_for_end_count)
async def process_end_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0:
            await message.answer("❌ Количество участников должно быть больше 0.")
            return
        await state.update_data(end_count=count, end_type="count")
        await message.answer("✅ Количество участников для завершения сохранено.")
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    
    await finish_giveaway_creation(message, state)

async def finish_giveaway_creation(message: Message, state: FSMContext):
    data = await state.get_data()
    
    required_fields = ['text', 'button_text', 'winners_count', 'channel_id', 'publish_time', 'end_type']
    for field in required_fields:
        if field not in data:
            await message.answer(f"❌ Ошибка: отсутствует поле {field}")
            await state.clear()
            return
    
    text = data.get('text', '')
    media_type = data.get('media_type')
    media_file_id = data.get('media_file_id')
    button_text = data.get('button_text', 'Участвовать')
    channels = data.get('channels', [])
    winners_count = data.get('winners_count', 1)
    channel_username = data.get('channel_id')
    publish_time = data.get('publish_time', 'сейчас')
    end_type = data.get('end_type')
    end_time = data.get('end_time')
    end_count = data.get('end_count')

    cursor.execute("SELECT channel_name FROM channels WHERE channel_username = ?", (channel_username,))
    row = cursor.fetchone()
    channel_name = row[0] if row else channel_username

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO giveaways (text, media_type, media_file_id, button_text, channels, winners_count, channel_id, publish_time, end_type, end_time, end_count, created_at, check_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            text, media_type, media_file_id, button_text, ','.join(channels), winners_count, channel_username, publish_time, end_type, end_time, end_count, current_time, ''
        ))
        conn.commit()
        giveaway_id = cursor.lastrowid
        print(f"✅ Розыгрыш сохранен в БД с ID: {giveaway_id}")
    except Exception as e:
        print(f"❌ Ошибка при сохранении в базу данных: {e}")
        await message.answer(f"❌ Ошибка при сохранении в базу данных: {e}")
        await state.clear()
        return

    if end_type == "time":
        end_info = f"по времени: {end_time}"
    else:
        end_info = f"по достижению {end_count} участников"

    preview_text = f"📋 Предпросмотр розыгрыша:\n\n{text}\n\n🔚 Розыгрыш завершится: {end_info}\n🏆 Количество победителей: {winners_count}\n📢 Канал: {channel_name}"
    
    try:
        if media_type and media_file_id:
            if media_type == "photo":
                await message.answer_photo(media_file_id, caption=preview_text)
            elif media_type == "video":
                await message.answer_video(media_file_id, caption=preview_text)
            elif media_type == "gif":
                await message.answer_animation(media_file_id, caption=preview_text)
        else:
            await message.answer(preview_text)
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке предпросмотра: {e}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить розыгрыш", callback_data=f"save_{giveaway_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_giveaway")]
    ])
    await message.answer("Сохранить розыгрыш?", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("save_"))
async def save_giveaway(call: CallbackQuery, state: FSMContext):
    giveaway_id = int(call.data.split("_")[1])
    print(f"🔄 Сохранение розыгрыша с ID: {giveaway_id}")
    
    try:
        success = await publish_giveaway_to_channel(giveaway_id)
        
        if success:
            await call.message.edit_text("✅ Розыгрыш сохранен и опубликован в канале!")
            print(f"✅ Розыгрыш {giveaway_id} успешно опубликован")
        else:
            await call.message.edit_text("❌ Розыгрыш сохранен, но не удалось опубликовать в канале. Проверьте права бота.")
            print(f"❌ Ошибка публикации розыгрыша {giveaway_id}")
        
        await state.clear()
        
    except Exception as e:
        print(f"❌ Критическая ошибка при сохранении розыгрыша: {e}")
        await call.message.edit_text("❌ Произошла ошибка при сохранении розыгрыша. Попробуйте еще раз.")
    
    await call.answer()

@dp.callback_query(F.data == "cancel_giveaway")
async def cancel_giveaway(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Создание розыгрыша отменено.")
    await call.answer()

@dp.callback_query(F.data == "my_channels")
async def my_channels(call: CallbackQuery):
    user_id = call.from_user.id
    cursor.execute("SELECT id, channel_name, channel_username FROM channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    channels = [(row[0], row[1], row[2]) for row in rows]

    if not channels:
        await call.message.answer("🗒 Добавленные вами каналы:\n\n❌ У вас нет добавленных каналов.")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить новый канал", callback_data="add_channel")]
        ])
        await call.message.answer("Выберите действие:", reply_markup=keyboard)
        await call.answer()
        return

    channels_text = "🗒 Добавленные вами каналы:\n\n" + "\n".join([f"• {channel_name}" for _, channel_name, _ in channels])
    
    keyboard_buttons = []
    for channel_id, channel_name, channel_username in channels:
        keyboard_buttons.append([InlineKeyboardButton(text=channel_name, callback_data=f"view_channel_{channel_id}")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить новый канал", callback_data="add_channel")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await call.message.answer(channels_text, reply_markup=keyboard)
    await call.answer()

@dp.message(Command("my_channels"))
async def cmd_my_channels(message: Message):
    user_id = message.from_user.id
    cursor.execute("SELECT id, channel_name, channel_username FROM channels WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    channels = [(row[0], row[1], row[2]) for row in rows]

    if not channels:
        await message.answer("🗒 Добавленные вами каналы:\n\n❌ У вас нет добавленных каналов.")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить новый канал", callback_data="add_channel")]
        ])
        await message.answer("Выберите действие:", reply_markup=keyboard)
        return

    channels_text = "🗒 Добавленные вами каналы:\n\n" + "\n".join([f"• {channel_name}" for _, channel_name, _ in channels])
    
    keyboard_buttons = []
    for channel_id, channel_name, channel_username in channels:
        keyboard_buttons.append([InlineKeyboardButton(text=channel_name, callback_data=f"view_channel_{channel_id}")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="➕ Добавить новый канал", callback_data="add_channel")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(channels_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("view_channel_"))
async def view_channel(call: CallbackQuery):
    channel_id = int(call.data.split("view_channel_")[1])
    
    cursor.execute("SELECT channel_name, channel_username FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    
    if not row:
        await call.answer("❌ Канал не найден")
        return
    
    channel_name, channel_username = row
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить из бота", callback_data=f"delete_channel_{channel_id}")]
    ])
    
    await call.message.answer(
        f"🗒 Меню канала:\n\n"
        f"📢 Название: {channel_name}\n"
        f"🔗 Username: {channel_username}",
        reply_markup=keyboard
    )
    await call.answer()

@dp.callback_query(F.data.startswith("delete_channel_"))
async def delete_channel_prompt(call: CallbackQuery):
    channel_id = int(call.data.split("delete_channel_")[1])
    
    cursor.execute("SELECT channel_name FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    
    if not row:
        await call.answer("❌ Канал не найден")
        return
    
    channel_name = row[0]
    
    await call.message.answer(
        f"⚠️ Чтобы удалить канал из бота, введите команду:\n"
        f"<code>/delete_channel {channel_id}</code>\n\n"
        f"Канал: {channel_name}",
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(Command("delete_channel"))
async def delete_channel(message: Message):
    if len(message.text.split()) < 2:
        await message.answer("❌ Использование: /delete_channel <ID_канала>")
        return
    
    try:
        channel_id = int(message.text.split()[1])
    except ValueError:
        await message.answer("❌ Неверный формат ID канала")
        return
    
    user_id = message.from_user.id
    cursor.execute("SELECT channel_name FROM channels WHERE id = ? AND user_id = ?", (channel_id, user_id))
    row = cursor.fetchone()
    
    if not row:
        await message.answer("❌ Канал не найден или у вас нет прав для его удаления")
        return
    
    channel_name = row[0]
    
    cursor.execute("DELETE FROM channels WHERE id = ? AND user_id = ?", (channel_id, user_id))
    conn.commit()
    
    await message.answer(f"✅ Канал '{channel_name}' успешно удален из бота")

@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        "📋 Инструкция:\n\n"
        "➕ Добавьте бота @carniz_bot в ваш канал или чат как администратора с правом публикации сообщений.\n\n"
        "После этого отправьте мне канал в формате:\n"
        "• @юзернеймканала\n"
        "• Или перешлите любое сообщение из канала\n"
        "• Или отправьте ссылку на канал\n\n"
        "Если вы хотите добавить приватный канал:\n"
        "• Перешлите из него сообщение\n"
        "• Или скопируйте и пришлите боту ссылку на любое сообщение из приватного канала\n\n"
        "💬 Если вы хотите использовать бота в группе (чате), обязательно выдайте ему право писать в ней."
    )
    await state.set_state(AddChannel.waiting_for_channel)
    await call.answer()

@dp.message(AddChannel.waiting_for_channel)
async def process_add_channel(message: Message, state: FSMContext):
    user_id = message.from_user.id
    channel_id = None
    channel_name = None
    channel_username = None

    if message.forward_from_chat:
        channel_id = str(message.forward_from_chat.id)
        channel_name = message.forward_from_chat.title
        channel_username = f"@{message.forward_from_chat.username}" if message.forward_from_chat.username else channel_id
        
        if not await is_bot_admin_in_channel(channel_id):
            await message.answer(
                "❌ Ошибка: бот не администратор этого канала!\n"
                "❗️ Проверять подписки на каналы могут только админы, "
                "добавьте бота в администраторы канала и пришлите ссылку на канал или перешлите любой пост из канала боту еще раз."
            )
            return
            
    elif message.text:
        text = message.text.strip()
        if text.startswith("https://t.me/"):
            if "joinchat" in text or "join/" in text:
                await message.answer(
                    "❌ Бота нельзя добавить в канал по ссылке-приглашению. "
                    "Если вы хотите добавить приватный канал, "
                    "скопируйте ссылку на любое сообщение из канала и пришлите ее боту."
                )
                return
            
            if "t.me/" in text:
                username = text.split("t.me/")[-1].split("/")[0]
                if username.startswith("+"):
                    await message.answer(
                        "❌ Бота нельзя добавить в канал по ссылке-приглашению. "
                        "Если вы хотите добавить приватный канал, "
                        "скопируйте ссылку на любое сообщение из канала и пришлите ее боту."
                    )
                    return
                channel_username = f"@{username}"
                channel_id = channel_username
            else:
                await message.answer("❌ Неверный формат ссылки.")
                return
                
        elif text.startswith("@"):
            channel_username = text
            channel_id = channel_username
        else:
            await message.answer("❌ Неверный формат. Используйте @username или ссылку на канал.")
            return

        if not await is_bot_admin_in_channel(channel_id):
            await message.answer(
                "❌ Ошибка: бот не администратор этого канала!\n"
                "❗️ Проверять подписки на каналы могут только админы, "
                "добавьте бота в администраторы канала и пришлите ссылку на канал или перешлите любой пост из канала боту еще раз."
            )
            return

        try:
            chat = await bot.get_chat(chat_id=channel_id)
            channel_name = chat.title or channel_id
            if not channel_username and chat.username:
                channel_username = f"@{chat.username}"
        except Exception as e:
            await message.answer(f"❌ Ошибка при получении информации о канале: {e}")
            return

    if channel_id and channel_name:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO channels (user_id, channel_id, channel_username, channel_name) VALUES (?, ?, ?, ?)", 
                (user_id, str(channel_id), str(channel_username or channel_id), channel_name)
            )
            conn.commit()
            
            await message.answer(
                f"✅ Канал '{channel_name}' добавлен, можно переходить к созданию розыгрыша!\n"
                f"Чтобы создать новый розыгрыш, введите команду /new_lot или нажмите кнопку 'Создать розыгрыш 🎁'"
            )
            await state.clear()
            
        except Exception as e:
            await message.answer(f"❌ Ошибка при добавлении канала: {e}")
    else:
        await message.answer("❌ Не удалось определить канал. Попробуйте еще раз.")

@dp.callback_query(F.data == "my_giveaways")
async def my_giveaways(call: CallbackQuery):
    user_id = call.from_user.id
    cursor.execute(
        "SELECT g.id, g.text, c.channel_name, g.winners_count, g.is_published FROM giveaways g "
        "JOIN channels c ON g.channel_id = c.channel_username WHERE c.user_id = ?", 
        (user_id,)
    )
    rows = cursor.fetchall()
    
    if not rows:
        await call.message.answer("❌ У вас нет созданных розыгрышей.")
        await call.answer()
        return
    
    text = "📋 Ваши розыгрыши:\n\n"
    for row in rows:
        giveaway_id, giveaway_text, channel_name, winners_count, is_published = row
        preview = giveaway_text[:50] + "..." if len(giveaway_text) > 50 else giveaway_text
        status = "✅ Опубликован" if is_published else "⏳ Ожидает публикации"
        text += f"🎁 ID: {giveaway_id}\n📝 {preview}\n🏆 Победителей: {winners_count}\n📢 Канал: {channel_name}\n📊 Статус: {status}\n\n"
    
    await call.message.answer(text)
    await call.answer()

@dp.message(Command("my_lots"))
async def cmd_my_lots(message: Message):
    user_id = message.from_user.id
    cursor.execute(
        "SELECT g.id, g.text, c.channel_name, g.winners_count, g.is_published FROM giveaways g "
        "JOIN channels c ON g.channel_id = c.channel_username WHERE c.user_id = ?", 
        (user_id,)
    )
    rows = cursor.fetchall()
    
    if not rows:
        await message.answer("❌ У вас нет созданных розыгрышей.")
        return
    
    text = "📋 Ваши розыгрыши:\n\n"
    for row in rows:
        giveaway_id, giveaway_text, channel_name, winners_count, is_published = row
        preview = giveaway_text[:50] + "..." if len(giveaway_text) > 50 else giveaway_text
        status = "✅ Опубликован" if is_published else "⏳ Ожидает публикации"
        text += f"🎁 ID: {giveaway_id}\n📝 {preview}\n🏆 Победителей: {winners_count}\n📢 Канал: {channel_name}\n📊 Статус: {status}\n\n"
    
    await message.answer(text)

scheduler = None

async def main():
    global scheduler
    await setup_commands(bot)
    scheduler = AsyncIOScheduler()
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
