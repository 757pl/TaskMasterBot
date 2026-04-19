import os
import sqlite3
from datetime import datetime, time as datetime_time, timedelta
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters)
from dotenv import load_dotenv
from database import *

# Добавляем колонку due_time, если её нет
conn = sqlite3.connect('tasks.db')
cur = conn.cursor()
try:
    cur.execute('ALTER TABLE tasks ADD COLUMN due_time TEXT DEFAULT "07:00"')
    print("✅ Колонка due_time добавлена")
except sqlite3.OperationalError:
    print("ℹ️ Колонка due_time уже есть")
conn.commit()
conn.close()
# ========== ПОДКЛЮЧЕНИЕ ==========
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
app = ApplicationBuilder().token(TOKEN).build()

# ========== ИНИЦИАЛИЗАЦИЯ БД ==========
init_db()

# ========== АДМИН ID ==========
ADMIN_ID = 1657525561

def is_admin(user_id):
    return user_id == ADMIN_ID

# ========== ОЧИСТКА СТАРЫХ ЗАДАЧ ==========
def cleanup_old_completed_tasks():
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('DELETE FROM tasks WHERE is_done = 1 AND completed_date < ?', (cutoff_date,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted

# ========== НАПОМИНАНИЯ (каждую минуту) ==========
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone('Asia/Irkutsk')
    now = datetime.now(tz)
    today = now.strftime('%d.%m')
    current_time = now.strftime('%H:%M')
    
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id, id, task_text, due_date
        FROM tasks WHERE due_date = ? AND due_time <= ? AND is_done = 0
    ''', (today, current_time))
    tasks = cur.fetchall()
    conn.close()
    
    user_tasks = {}
    for user_id, task_id, task_text, due_date in tasks:
        if user_id not in user_tasks:
            user_tasks[user_id] = []
        user_tasks[user_id].append((task_id, task_text))
    
    for user_id, tasks_list in user_tasks.items():
        task_lines = "\n".join([f"🔹 `{tid}`. {ttext}" for tid, ttext in tasks_list])
        message = (
            f"🔔 **Напоминание!**\n\n"
            f"📅 **Сегодня ({today}) нужно сделать:**\n\n"
            f"{task_lines}\n\n"
            f"✅ Нажми «✅ Выполнено» в меню"
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
        except Exception as e:
            print(f"Ошибка: {e}")

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📚 Расписание"), KeyboardButton("📝 Задачи")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ О боте")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_tasks_keyboard():
    keyboard = [
        [KeyboardButton("📋 Активные задачи")],
        [KeyboardButton("➕ Добавить задачу"), KeyboardButton("✏ Редактировать задачу")],
        [KeyboardButton("✅ Выполнено"), KeyboardButton("🗑 Удалить задачу")],
        [KeyboardButton("📊 Выполненные задачи"), KeyboardButton("🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_completed_tasks_keyboard():
    keyboard = [
        [KeyboardButton("🗑 Удалить выполненную"), KeyboardButton("📋 Все выполненные")],
        [KeyboardButton("🔙 Назад в задачи")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ========== КОМАНДЫ ==========
async def start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 **Привет, {user.first_name}!**\n\n"
        "Я помогу не забывать о домашних заданиях.\n"
        "Используй кнопки внизу 👇",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def help_command(update, context):
    await update.message.reply_text(
        "🤖 **Помощь**\n\n"
        "📌 **Добавить задачу:**\n"
        "`/add 25.05 14:30 Сдать проект`\n"
        "Время можно не указывать (по умолчанию 07:00)\n\n"
        "📌 **Команды:**\n"
        "/add - добавить задачу\n"
        "/edit <номер> - редактировать\n"
        "/done <номер> - выполнить\n"
        "/delete <номер> - удалить\n"
        "/completed - список выполненных\n\n"
        "⏰ **Выполненные задачи удаляются через 14 дней**",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def about(update, context):
    await update.message.reply_text(
        "ℹ **О боте**\n\n"
        "📌 Учебный помощник\n"
        "⏰ Напоминания в выбранное время\n"
        "🗑 Выполненные задачи удаляются через 14 дней\n"
        "🛠 Python + SQLite",
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# ========== РАБОТА С ЗАДАЧАМИ ==========
async def add_task_command(update, context):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ **Формат:** `/add <дата> [время] <задача>`\n"
                "Примеры:\n"
                "`/add 25.05 Сдать проект` (время 07:00)\n"
                "`/add 25.05 14:30 Сдать проект`",
                parse_mode='Markdown'
            )
            return
        
        if len(args) >= 3 and ':' in args[1]:
            due_date = args[0]
            due_time = args[1]
            task_text = ' '.join(args[2:])
        else:
            due_date = args[0]
            due_time = '07:00'
            task_text = ' '.join(args[1:])
        
        user_id = update.effective_user.id
        add_task(user_id, task_text, due_date, due_time)
        await update.message.reply_text(f"✅ Задача добавлена на {due_date} в {due_time}!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def list_active_tasks(update, context):
    user_id = update.effective_user.id
    tasks = get_active_tasks(user_id)
    
    if not tasks:
        await update.message.reply_text("📭 Нет активных задач", reply_markup=get_tasks_keyboard())
        return
    
    text = "📋 **Активные задачи:**\n\n"
    for task_id, task_text, due_date, due_time in tasks:
        text += f"🔹 `{task_id}`. {task_text} — до {due_date} в {due_time}\n"
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_tasks_keyboard())

async def list_completed_tasks(update, context):
    user_id = update.effective_user.id
    tasks = get_completed_tasks(user_id)
    
    if not tasks:
        await update.message.reply_text("📭 Нет выполненных задач", reply_markup=get_completed_tasks_keyboard())
        return
    
    text = "✅ **Выполненные задачи:**\n\n"
    for task_id, task_text, due_date, due_time, completed_date in tasks:
        comp_date = completed_date[:16] if completed_date else "неизвестно"
        text += f"🔹 `{task_id}`. {task_text}\n   📅 Сделано: {comp_date}\n   🗑 Удалится через 14 дней\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_completed_tasks_keyboard())

async def done_task_command(update, context):
    try:
        task_id = int(context.args[0])
        user_id = update.effective_user.id
        complete_task(task_id, user_id)
        await update.message.reply_text(f"✅ Задача {task_id} выполнена!\n\nОна появится в «Выполненные задачи» и удалится через 14 дней.")
    except:
        await update.message.reply_text("❌ Используй: `/done <номер>`\nНомер из «Активные задачи»", parse_mode='Markdown')

async def delete_task_command(update, context):
    try:
        task_id = int(context.args[0])
        user_id = update.effective_user.id
        delete_task(task_id, user_id)
        await update.message.reply_text(f"✅ Задача {task_id} удалена")
    except:
        await update.message.reply_text("❌ Используй: `/delete <номер>`", parse_mode='Markdown')

async def delete_completed_task_command(update, context):
    try:
        task_id = int(context.args[0])
        user_id = update.effective_user.id
        delete_completed_task(task_id, user_id)
        await update.message.reply_text(f"✅ Выполненная задача {task_id} удалена досрочно")
    except:
        await update.message.reply_text("❌ Используй: `/delcomp <номер>`\nНомер из «Выполненные задачи»", parse_mode='Markdown')

# ========== РЕДАКТИРОВАНИЕ ==========
async def edit_task_command(update, context):
    try:
        task_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Используй: `/edit <номер>`", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    task = get_task_by_id(task_id, user_id)
    if not task:
        await update.message.reply_text("❌ Задача не найдена или уже выполнена")
        return
    
    context.user_data['editing'] = {'task_id': task_id, 'step': 'text'}
    await update.message.reply_text(
        f"✏ **Редактируем:**\nТекущий текст: `{task[1]}`\n\n"
        "Введи **новый текст** (или `-` чтобы оставить):",
        parse_mode='Markdown'
    )

async def handle_edit(update, context):
    if 'editing' not in context.user_data:
        return False
    
    edit = context.user_data['editing']
    task_id = edit['task_id']
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if edit['step'] == 'text':
        if text != '-':
            update_task(task_id, user_id, task_text=text)
        edit['step'] = 'date'
        await update.message.reply_text("Введи **новую дату** (ДД.ММ) или `-`:")
        return True
    
    elif edit['step'] == 'date':
        if text != '-':
            update_task(task_id, user_id, due_date=text)
        edit['step'] = 'time'
        await update.message.reply_text("Введи **новое время** (ЧЧ:ММ) или `-`:")
        return True
    
    elif edit['step'] == 'time':
        if text != '-':
            update_task(task_id, user_id, due_time=text)
        del context.user_data['editing']
        await update.message.reply_text("✅ Задача обновлена!", reply_markup=get_tasks_keyboard())
        return True
    
    return False

# ========== РАСПИСАНИЕ ==========
async def schedule(update, context):
    text = (
        "📅 **Расписание 10Г**\n\n"
        "**Понедельник:**\n1️⃣ Алгебра (7)\n2️⃣ Алгебра (7)\n3️⃣ Обществознание (19)\n4️⃣ Обществознание (19)\n5️⃣ ОБЗР (43)\n6️⃣ Английский язык (46)\n7️⃣ Английский язык (46)\n\n"
        "**Вторник:**\n1️⃣ Инд.проект (204)\n2️⃣ Физика (204)\n3️⃣ Биология (5)\n4️⃣ География (203)\n5️⃣ Геометрия (7)\n6️⃣ Литература (206)\n7️⃣ Литература (206)\n\n"
        "**Среда:**\n1️⃣ Информатика (205/306)\n2️⃣ Информатика (205/306)\n3️⃣ Алгебра (7)\n4️⃣ Алгебра (7)\n5️⃣ Физ-ра\n6️⃣ Русский язык (18)\n7️⃣ Русский язык (18)\n\n"
        "**Четверг:**\n1️⃣ История (19)\n2️⃣ История (19)\n3️⃣ Физ-ра\n4️⃣ Геометрия (7)\n5️⃣ Геометрия (7)\n6️⃣ Литература (206)\n7️⃣ Классный час (204)\n\n"
        "**Пятница:**\n1️⃣ Алгебра (7)\n2️⃣ Вероятность (7)\n3️⃣ Химия (15)\n4️⃣ Физика (18)\n5️⃣ Информатика (205/306)\n6️⃣ Информатика (205/306)\n7️⃣ Английский язык (46)"
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard())

# ========== АДМИН ==========
async def admin_cleanup(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа")
        return
    deleted = cleanup_old_completed_tasks()
    await update.message.reply_text(f"🗑 Удалено старых выполненных задач: {deleted}")

# ========== ОБРАБОТЧИК КНОПОК ==========
async def handle_text(update, context):
    if await handle_edit(update, context):
        return
    
    text = update.message.text
    
    if text == "📚 Расписание":
        await schedule(update, context)
    
    elif text == "📝 Задачи":
        await update.message.reply_text("📝 **Управление задачами**\n\nВыбери действие:", parse_mode='Markdown', reply_markup=get_tasks_keyboard())
    
    elif text == "📋 Активные задачи":
        await list_active_tasks(update, context)
    
    elif text == "➕ Добавить задачу":
        await update.message.reply_text("📝 Отправь командой:\n`/add <дата> [время] <задача>`\nПример: `/add 25.05 14:30 Сдать проект`", parse_mode='Markdown')
    
    elif text == "✅ Выполнено":
        await update.message.reply_text("Введи `/done <номер задачи>`\nНомер из «Активные задачи»", parse_mode='Markdown')
    
    elif text == "✏ Редактировать задачу":
        await update.message.reply_text("Введи `/edit <номер задачи>`\nНомер из «Активные задачи»", parse_mode='Markdown')
    
    elif text == "🗑 Удалить задачу":
        await update.message.reply_text("Введи `/delete <номер задачи>`\nНомер из «Активные задачи»", parse_mode='Markdown')
    
    elif text == "📊 Выполненные задачи":
        await list_completed_tasks(update, context)
    
    elif text == "🗑 Удалить выполненную":
        await update.message.reply_text("Введи `/delcomp <номер задачи>`\nНомер из «Выполненные задачи»", parse_mode='Markdown')
    
    elif text == "📋 Все выполненные":
        await list_completed_tasks(update, context)
    
    elif text == "🔙 Назад в задачи":
        await update.message.reply_text("📝 Управление задачами:", reply_markup=get_tasks_keyboard())
    
    elif text == "🔙 Назад в меню":
        await start(update, context)
    
    elif text == "❓ Помощь":
        await help_command(update, context)
    
    elif text == "ℹ О боте":
        await about(update, context)
    
    else:
        await update.message.reply_text("❓ Не понял. Используй кнопки меню 👇", reply_markup=get_main_keyboard())

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_task_command))
    app.add_handler(CommandHandler("edit", edit_task_command))
    app.add_handler(CommandHandler("done", done_task_command))
    app.add_handler(CommandHandler("delete", delete_task_command))
    app.add_handler(CommandHandler("delcomp", delete_completed_task_command))
    app.add_handler(CommandHandler("completed", list_completed_tasks))
    app.add_handler(CommandHandler("admin_cleanup", admin_cleanup))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск напоминаний (каждую минуту)
    app.job_queue.run_repeating(check_reminders, interval=60, first=10)
    
    # Очистка старых задач при запуске
    # try:
    #     cleanup_old_completed_tasks()
    #     print("🧹 Очистка старых задач выполнена")
    # except Exception as e:
    #     print(f"⚠️ Ошибка очистки: {e}")
    
    print("✅ Бот запущен!")
    app.run_polling()
