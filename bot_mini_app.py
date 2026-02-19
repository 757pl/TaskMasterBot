import os
import sqlite3
from datetime import datetime, timedelta, time as datetime_time
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters)
from dotenv import load_dotenv
from telegram import WebAppInfo
import json

# ========== ПОДКЛЮЧЕНИЕ ==========
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
app = ApplicationBuilder().token(TOKEN).build()

# ========== БАЗА ДАННЫХ SQLite ==========
def init_db():
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_text TEXT,
            due_date TEXT,
            created_date TEXT,
            is_done INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

def add_task_db(user_id, task_text, due_date):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO tasks (user_id, task_text, due_date, created_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, task_text, due_date, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id

def get_tasks_db(user_id, only_active=True):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    
    if only_active:
        cur.execute('''
            SELECT id, task_text, due_date, created_date FROM tasks 
            WHERE user_id = ? AND is_done = 0
            ORDER BY due_date
        ''', (user_id,))
    else:
        cur.execute('''
            SELECT id, task_text, due_date, is_done, created_date FROM tasks 
            WHERE user_id = ?
            ORDER BY due_date
        ''', (user_id,))
    
    tasks = cur.fetchall()
    conn.close()
    return tasks

def done_task_db(task_id, user_id):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('''
        UPDATE tasks SET is_done = 1 
        WHERE id = ? AND user_id = ?
    ''', (task_id, user_id))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success

def delete_task_db(task_id, user_id):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success

# ========== АДМИН-ФУНКЦИИ ==========
ADMIN_ID = 1657525561

def is_admin(user_id):
    return user_id == ADMIN_ID

def get_all_users():
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id, first_name, username, joined_date FROM users ORDER BY joined_date DESC')
    users = cur.fetchall()
    conn.close()
    return users

def get_user_stats():
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM users')
    total_users = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM tasks')
    total_tasks = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM tasks WHERE is_done = 0')
    active_tasks = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM tasks WHERE is_done = 1')
    done_tasks = cur.fetchone()[0]
    
    conn.close()
    return total_users, total_tasks, active_tasks, done_tasks

def delete_user_by_id(target_user_id):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    
    cur.execute('DELETE FROM tasks WHERE user_id = ?', (target_user_id,))
    tasks_deleted = cur.rowcount
    
    cur.execute('DELETE FROM users WHERE user_id = ?', (target_user_id,))
    user_deleted = cur.rowcount > 0
    
    conn.commit()
    conn.close()
    
    return user_deleted, tasks_deleted

def find_user_by_id(user_id):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT first_name, username, joined_date FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

# ========== НАПОМИНАНИЯ (7:00 УЛАН-УДЭ) ==========
async def send_daily_reminders(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('school_bot.db')
    cur = conn.cursor()
    
    tz = pytz.timezone('Asia/Irkutsk')
    today = datetime.now(tz).strftime('%d.%m')
    
    cur.execute('''
        SELECT user_id, id, task_text, due_date 
        FROM tasks 
        WHERE due_date = ? AND is_done = 0
        ORDER BY user_id
    ''', (today,))
    
    tasks_today = cur.fetchall()
    conn.close()
    
    if not tasks_today:
        print(f"📅 {today}: нет задач на сегодня")
        return
    
    user_tasks = {}
    for user_id, task_id, task_text, due_date in tasks_today:
        if user_id not in user_tasks:
            user_tasks[user_id] = []
        user_tasks[user_id].append((task_id, task_text))
    
    sent_count = 0
    for user_id, tasks in user_tasks.items():
        try:
            task_list = "\n".join([f"🔹 `{tid}`. {ttext}" for tid, ttext in tasks])
            message = (
                f"🔔 **Доброе утро! ☀️**\n\n"
                f"📅 **Сегодня ({today}) нужно сделать:**\n\n"
                f"{task_list}\n\n"
                f"✅ Отметь выполненные: нажми «✅ Выполнено» и введи номер"
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception as e:
            print(f"❌ Ошибка при отправке пользователю {user_id}: {e}")
    
    print(f"✅ Напоминания отправлены {sent_count} пользователям в {today}")

# Инициализация БД
init_db()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📚 Расписание"), KeyboardButton("📝 Задания")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ О боте")],
        [KeyboardButton("👑 Админ-панель")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_schedule_keyboard():
    keyboard = [
        [KeyboardButton("📅 Понедельник"), KeyboardButton("📅 Вторник")],
        [KeyboardButton("📅 Среда"), KeyboardButton("📅 Четверг")],
        [KeyboardButton("📅 Пятница")],
        [KeyboardButton("🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_tasks_keyboard():
    keyboard = [
        [KeyboardButton("📋 Мои задачи"), KeyboardButton("➕ Добавить задачу")],
        [KeyboardButton("✅ Выполнено"), KeyboardButton("❌ Удалить задачу")],
        [KeyboardButton("🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 Статистика"), KeyboardButton("👥 Список пользователей")],
        [KeyboardButton("🗑 Удалить пользователя"), KeyboardButton("🔍 Найти пользователя")],
        [KeyboardButton("🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== КОМАНДЫ ==========
async def web_app_data(update, context):
    """Получает данные из Mini App"""
    data = json.loads(update.effective_message.web_app_data.data)
    user_id = update.effective_user.id
    
    if data['action'] == 'get_tasks':
        tasks = get_tasks_db(user_id, only_active=False)
        # Отправляем задачи обратно в Mini App
        await update.effective_message.reply_text(
            json.dumps({
                'action': 'tasks_loaded',
                'tasks': [
                    {
                        'id': t[0],
                        'task_text': t[1],
                        'due_date': t[2],
                        'is_done': t[3] if len(t) > 3 else 0,
                        'created_date': t[4] if len(t) > 4 else ''
                    }
                    for t in tasks
                ]
            })
        )
    
    elif data['action'] == 'add_task':
        task_id = add_task_db(
            user_id, 
            data['task_text'], 
            data['due_date']
        )
        await update.effective_message.reply_text(
            json.dumps({'action': 'task_added', 'task_id': task_id})
        )
    
    elif data['action'] == 'toggle_task':
        done_task_db(data['task_id'], user_id)
        await update.effective_message.reply_text(
            json.dumps({'action': 'task_toggled'})
        )
    
    elif data['action'] == 'delete_task':
        delete_task_db(data['task_id'], user_id)
        await update.effective_message.reply_text(
            json.dumps({'action': 'task_deleted'})
        )

async def webapp(update, context):
    """Открывает Mini App"""
    keyboard = [
        [KeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(url="https://твой-сайт.com"))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "📱 Нажми кнопку, чтобы открыть приложение:",
        reply_markup=reply_markup
    )

async def start(update, context):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        f"👋 **Привет, {user.first_name}!**\n\n"
        "Я помогу тебе не забывать о домашних заданиях.\n"
        "Используй кнопки внизу экрана 👇",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def help_command(update, context):
    await update.message.reply_text(
        "🤖 **Помощь по боту**\n\n"
        "📌 **Кнопки:**\n"
        "• Расписание - уроки 10Г\n"
        "• Задания - управление задачами\n"
        "• Помощь - подсказка\n"
        "• О боте - информация\n\n"
        "⏰ **Напоминания каждый день в 7:00**",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def about(update, context):
    await update.message.reply_text(
        "ℹ **О боте**\n\n"
        "📌 Учебный бот-помощник\n"
        "👨‍💻 Разработчик: ученик\n"
        "⏰ Напоминания: каждый день в 7:00\n"
        "🛠 Технологии: Python + SQLite",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def my_id(update, context):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 Твой ID: `{user_id}`", parse_mode='Markdown')

# ========== АДМИН-КОМАНДЫ ==========
async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    await update.message.reply_text(
        "👑 **Админ-панель**\n\nВыбери действие:",
        parse_mode='Markdown',
        reply_markup=get_admin_keyboard()
    )

async def admin_stats(update, context):
    if not is_admin(update.effective_user.id):
        return
    
    total_users, total_tasks, active_tasks, done_tasks = get_user_stats()
    
    stats_text = (
        "📊 **Статистика бота**\n\n"
        f"👥 Пользователей: `{total_users}`\n"
        f"📝 Всего задач: `{total_tasks}`\n"
        f"✅ Активных: `{active_tasks}`\n"
        f"✔ Выполненных: `{done_tasks}`\n"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def admin_list_users(update, context):
    if not is_admin(update.effective_user.id):
        return
    
    users = get_all_users()
    if not users:
        await update.message.reply_text("📭 Нет пользователей")
        return
    
    text = "👥 **Список пользователей:**\n\n"
    for user_id, first_name, username, joined_date in users:
        username_text = f"@{username}" if username else "нет username"
        text += f"🆔 `{user_id}` | {first_name} | {username_text}\n📅 {joined_date}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_find_user(update, context):
    if not is_admin(update.effective_user.id):
        return
    
    context.user_data['admin_finding_user'] = True
    await update.message.reply_text(
        "🔍 Введи ID пользователя:",
        reply_markup=get_admin_keyboard()
    )

async def admin_delete_user_start(update, context):
    if not is_admin(update.effective_user.id):
        return
    
    context.user_data['admin_deleting_user'] = True
    await update.message.reply_text(
        "🗑 Введи ID пользователя для удаления:",
        reply_markup=get_admin_keyboard()
    )

# ========== ТЕСТ НАПОМИНАНИЙ ==========
async def test_reminder(update, context):
    if is_admin(update.effective_user.id):
        await send_daily_reminders(context)
        await update.message.reply_text("✅ Тестовые напоминания отправлены!")

# ========== ОБРАБОТЧИК ТЕКСТА ==========
async def handle_text(update, context):
    text = update.message.text
    user_id = update.effective_user.id
    
    # Админ-режимы
    if context.user_data.get('admin_finding_user'):
        try:
            target_id = int(text.strip())
            user = find_user_by_id(target_id)
            if user:
                first_name, username, joined_date = user
                username_text = f"@{username}" if username else "нет username"
                await update.message.reply_text(
                    f"👤 **Найден пользователь:**\n\n"
                    f"🆔 ID: `{target_id}`\n"
                    f"👤 Имя: {first_name}\n"
                    f"📱 Username: {username_text}\n"
                    f"📅 Дата: {joined_date}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Пользователь не найден")
            context.user_data['admin_finding_user'] = False
        except:
            await update.message.reply_text("❌ Введи ID цифрами")
        return
    
    if context.user_data.get('admin_deleting_user'):
        try:
            target_id = int(text.strip())
            if target_id == ADMIN_ID:
                await update.message.reply_text("❌ Нельзя удалить себя")
            else:
                user_deleted, tasks_deleted = delete_user_by_id(target_id)
                if user_deleted:
                    await update.message.reply_text(f"✅ Пользователь {target_id} удалён\n📝 Задач: {tasks_deleted}")
                else:
                    await update.message.reply_text("❌ Пользователь не найден")
            context.user_data['admin_deleting_user'] = False
        except:
            await update.message.reply_text("❌ Введи ID цифрами")
        return
    
    # Главное меню
    if text == "📚 Расписание":
        await update.message.reply_text(
            "📅 Выбери день недели:",
            reply_markup=get_schedule_keyboard()
        )
    
    elif text == "📝 Задания":
        await update.message.reply_text(
            "📝 **Управление задачами**\n\n"
            "Выбери действие:",
            parse_mode='Markdown',
            reply_markup=get_tasks_keyboard()
        )
    
    elif text == "❓ Помощь":
        await help_command(update, context)
    
    elif text == "ℹ О боте":
        await about(update, context)
    
    elif text == "👑 Админ-панель":
        await admin_panel(update, context)
    
    # Админ-меню
    elif text == "📊 Статистика":
        await admin_stats(update, context)
    
    elif text == "👥 Список пользователей":
        await admin_list_users(update, context)
    
    elif text == "🗑 Удалить пользователя":
        await admin_delete_user_start(update, context)
    
    elif text == "🔍 Найти пользователя":
        await admin_find_user(update, context)
    
    # Расписание 10Г
    elif text == "📅 Понедельник":
        days = [
            "1️⃣ Алгебра (7)", "2️⃣ Алгебра (7)",
            "3️⃣ Обществознание (19)", "4️⃣ Обществознание (19)",
            "5️⃣ ОБЗР (43)", "6️⃣ Английский язык (46)",
            "7️⃣ Английский язык (46)"
        ]
        await update.message.reply_text(
            "📅 **10Г — Понедельник**\n\n" + "\n".join(days),
            parse_mode='Markdown',
            reply_markup=get_schedule_keyboard()
        )

    elif text == "📅 Вторник":
        days = [
            "1️⃣ Инд.проект (204)", "2️⃣ Физика (204)",
            "3️⃣ Биология (5)", "4️⃣ География (203)",
            "5️⃣ Геометрия (7)", "6️⃣ Литература (206)",
            "7️⃣ Литература (206)"
        ]
        await update.message.reply_text(
            "📅 **10Г — Вторник**\n\n" + "\n".join(days),
            parse_mode='Markdown',
            reply_markup=get_schedule_keyboard()
        )

    elif text == "📅 Среда":
        days = [
            "1️⃣ Информатика (205/306)", "2️⃣ Информатика (205/306)",
            "3️⃣ Алгебра (7)", "4️⃣ Алгебра (7)",
            "5️⃣ Физ-ра", "6️⃣ Русский язык (18)",
            "7️⃣ Русский язык (18)"
        ]
        await update.message.reply_text(
            "📅 **10Г — Среда**\n\n" + "\n".join(days),
            parse_mode='Markdown',
            reply_markup=get_schedule_keyboard()
        )

    elif text == "📅 Четверг":
        days = [
            "1️⃣ История (19)", "2️⃣ История (19)",
            "3️⃣ Физ-ра", "4️⃣ Геометрия (7)",
            "5️⃣ Геометрия (7)", "6️⃣ Литература (206)",
            "7️⃣ Классный час (204)"
        ]
        await update.message.reply_text(
            "📅 **10Г — Четверг**\n\n" + "\n".join(days),
            parse_mode='Markdown',
            reply_markup=get_schedule_keyboard()
        )

    elif text == "📅 Пятница":
        days = [
            "1️⃣ Алгебра (7)", "2️⃣ Вероятность (7)",
            "3️⃣ Химия (15)", "4️⃣ Физика (18)",
            "5️⃣ Информатика (205/306)", "6️⃣ Информатика (205/306)",
            "7️⃣ Английский язык (46)"
        ]
        await update.message.reply_text(
            "📅 **10Г — Пятница**\n\n" + "\n".join(days),
            parse_mode='Markdown',
            reply_markup=get_schedule_keyboard()
        )
    
    # ===== МЕНЮ ЗАДАНИЙ =====
    elif text == "📋 Мои задачи":
        tasks = get_tasks_db(user_id, only_active=False)
        if not tasks:
            await update.message.reply_text(
                "📭 **У тебя пока нет задач**\n\n"
                "➕ Добавь первую через «➕ Добавить задачу»",
                parse_mode='Markdown',
                reply_markup=get_tasks_keyboard()
            )
        else:
            active_tasks = [t for t in tasks if t[3] == 0]
            done_tasks = [t for t in tasks if t[3] == 1]
            
            context.user_data['active_tasks'] = active_tasks
            
            response = f"📋 **Мои задачи**\n"
            response += f"┌ Активных: {len(active_tasks)}  |  Выполнено: {len(done_tasks)}\n\n"
            
            if active_tasks:
                response += "**⏳ Активные:**\n"
                for idx, task in enumerate(active_tasks, 1):
                    task_id, task_text, due_date, is_done, created_date = task
                    response += f"`{idx}`. {task_text}\n"
                    response += f"   📅 Сделать до: {due_date}\n"
                    response += f"   ✏️ Добавлена: {created_date[:10]}\n\n"
            
            if done_tasks:
                response += "**✅ Выполненные:**\n"
                for idx, task in enumerate(done_tasks, 1):
                    task_id, task_text, due_date, is_done, created_date = task
                    response += f"{idx}. ~~{task_text}~~\n"
                    response += f"   📅 Было до: {due_date}\n\n"
            
            response += "🔹 **Для действий вводи номера из списка (1, 2, 3...)**"
            
            await update.message.reply_text(response, parse_mode='Markdown')
    
    elif text == "➕ Добавить задачу":
        context.user_data['adding_task'] = True
        await update.message.reply_text(
            "📝 **Добавление задачи**\n\n"
            "📌 **Формат:** `<дата> <задача>`\n"
            "📅 Дата: ДД.ММ (например 25.05)\n"
            "📝 Задача: любой текст\n\n"
            "✅ **Пример:**\n"
            "`25.05 Сдать проект по информатике`",
            parse_mode='Markdown',
            reply_markup=get_tasks_keyboard()
        )
    
    elif text == "✅ Выполнено":
        context.user_data['waiting_for_done'] = True
        await update.message.reply_text(
            "✅ **Отметка выполнения**\n\n"
            "🔢 Введи **номера задач** из списка\n"
            "👆 Можно несколько через пробел: `1 3 5`",
            parse_mode='Markdown',
            reply_markup=get_tasks_keyboard()
        )
    
    elif text == "❌ Удалить задачу":
        keyboard = [
            [KeyboardButton("🗑 Удалить одну"), KeyboardButton("🗑 Удалить всё")],
            [KeyboardButton("🔙 Назад в меню")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "❌ **Удаление задач**\n\n"
            "Выбери действие:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif text == "🗑 Удалить одну":
        context.user_data['waiting_for_delete_one'] = True
        await update.message.reply_text(
            "❌ **Удаление одной задачи**\n\n"
            "🔢 Введи **номер задачи** из списка",
            parse_mode='Markdown',
            reply_markup=get_tasks_keyboard()
        )
    
    elif text == "🗑 Удалить всё":
        context.user_data['waiting_for_delete_all'] = True
        keyboard = [
            [KeyboardButton("✅ Да, удалить всё"), KeyboardButton("❌ Нет, отмена")],
            [KeyboardButton("🔙 Назад в меню")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "⚠️ **ВНИМАНИЕ!**\n\n"
            "Ты точно хочешь **удалить ВСЕ задачи**?\n"
            "Это действие нельзя отменить!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif text == "✅ Да, удалить всё":
        conn = sqlite3.connect('school_bot.db')
        cur = conn.cursor()
        cur.execute('DELETE FROM tasks WHERE user_id = ?', (user_id,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Все задачи удалены!**\n\n"
            f"🗑 Удалено задач: {deleted}",
            parse_mode='Markdown',
            reply_markup=get_tasks_keyboard()
        )
        context.user_data.pop('waiting_for_delete_all', None)
        context.user_data.pop('active_tasks', None)
    
    elif text == "❌ Нет, отмена":
        context.user_data.pop('waiting_for_delete_all', None)
        await update.message.reply_text(
            "✅ Удаление отменено",
            reply_markup=get_tasks_keyboard()
        )
    
    # Обработка добавления задачи
    elif context.user_data.get('adding_task'):
        try:
            parts = text.split(' ', 1)
            if len(parts) == 2:
                due_date = parts[0]
                task_text = parts[1]
                task_id = add_task_db(user_id, task_text, due_date)
                await update.message.reply_text(
                    f"✅ Задача добавлена на {due_date}!",
                    reply_markup=get_tasks_keyboard()
                )
                context.user_data['adding_task'] = False
            else:
                await update.message.reply_text(
                    "❌ Неправильный формат. Пример: `25.05 Сдать проект`",
                    parse_mode='Markdown',
                    reply_markup=get_tasks_keyboard()
                )
        except:
            await update.message.reply_text("❌ Ошибка", reply_markup=get_tasks_keyboard())
    
    # Обработка выполнения по номерам
    elif context.user_data.get('waiting_for_done'):
        try:
            active_tasks = context.user_data.get('active_tasks', [])
            if not active_tasks:
                tasks = get_tasks_db(user_id, only_active=False)
                active_tasks = [t for t in tasks if t[3] == 0]
            
            input_nums = [int(x.strip()) for x in text.split()]
            success_count = 0
            
            for num in input_nums:
                if 1 <= num <= len(active_tasks):
                    real_task_id = active_tasks[num-1][0]
                    if done_task_db(real_task_id, user_id):
                        success_count += 1
            
            if success_count > 0:
                await update.message.reply_text(
                    f"✅ Отмечено выполненных: {success_count}",
                    reply_markup=get_tasks_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Задачи не найдены. Проверь номера",
                    reply_markup=get_tasks_keyboard()
                )
            context.user_data['waiting_for_done'] = False
            context.user_data.pop('active_tasks', None)
        except:
            await update.message.reply_text(
                "❌ Введи номера цифрами через пробел\nПример: `1 3 5`",
                parse_mode='Markdown',
                reply_markup=get_tasks_keyboard()
            )
    
    # Обработка удаления одной по номеру
    elif context.user_data.get('waiting_for_delete_one'):
        try:
            tasks = get_tasks_db(user_id, only_active=False)
            active_tasks = [t for t in tasks if t[3] == 0]
            
            num = int(text.strip())
            if 1 <= num <= len(active_tasks):
                real_task_id = active_tasks[num-1][0]
                if delete_task_db(real_task_id, user_id):
                    await update.message.reply_text(
                        f"✅ Задача {num} удалена",
                        reply_markup=get_tasks_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        "❌ Ошибка удаления",
                        reply_markup=get_tasks_keyboard()
                    )
            else:
                await update.message.reply_text(
                    "❌ Нет задачи с таким номером",
                    reply_markup=get_tasks_keyboard()
                )
            context.user_data['waiting_for_delete_one'] = False
        except:
            await update.message.reply_text(
                "❌ Введи номер цифрой",
                reply_markup=get_tasks_keyboard()
            )

    # Неизвестная команда
    else:
        await update.message.reply_text(
            "❓ Не понял команду.\nИспользуй кнопки внизу 👇",
            reply_markup=get_main_keyboard()
        )

# ========== ПОДКЛЮЧЕНИЕ ОБРАБОТЧИКОВ ==========
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("myid", my_id))
app.add_handler(CommandHandler("testremind", test_reminder))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(CommandHandler("app", webapp))
app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    try:
        tz = pytz.timezone('Asia/Irkutsk')
        app.job_queue.run_daily(
            send_daily_reminders,
            time=datetime_time(hour=7, minute=0, tzinfo=tz),
            days=tuple(range(7))
        )
        print("⏰ Напоминания: каждый день в 7:00 (Улан-Удэ)")
    except Exception as e:
        print(f"⚠️ Ошибка настройки напоминаний: {e}")
    
    print("✅ Бот запущен!")
    print("📁 Файл БД: school_bot.db")
    print("📌 Нажми Ctrl+C для остановки")
    app.run_polling()