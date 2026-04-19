import sqlite3
from datetime import datetime, timedelta

def init_db():
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_text TEXT,
            due_date TEXT,
            due_time TEXT DEFAULT '07:00',
            completed_date TEXT,
            is_done INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def add_task(user_id, task_text, due_date, due_time='07:00'):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO tasks (user_id, task_text, due_date, due_time)
        VALUES (?, ?, ?, ?)
    ''', (user_id, task_text, due_date, due_time))
    conn.commit()
    conn.close()

def get_active_tasks(user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, task_text, due_date, due_time
        FROM tasks WHERE user_id = ? AND is_done = 0
        ORDER BY due_date
    ''', (user_id,))
    tasks = cur.fetchall()
    conn.close()
    return tasks

def get_completed_tasks(user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, task_text, due_date, due_time, completed_date
        FROM tasks WHERE user_id = ? AND is_done = 1
        ORDER BY completed_date DESC
    ''', (user_id,))
    tasks = cur.fetchall()
    conn.close()
    return tasks

def get_task_by_id(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, task_text, due_date, due_time
        FROM tasks WHERE id = ? AND user_id = ? AND is_done = 0
    ''', (task_id, user_id))
    task = cur.fetchone()
    conn.close()
    return task

def update_task(task_id, user_id, task_text=None, due_date=None, due_time=None):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    if task_text:
        cur.execute('UPDATE tasks SET task_text = ? WHERE id = ? AND user_id = ?', (task_text, task_id, user_id))
    if due_date:
        cur.execute('UPDATE tasks SET due_date = ? WHERE id = ? AND user_id = ?', (due_date, task_id, user_id))
    if due_time:
        cur.execute('UPDATE tasks SET due_time = ? WHERE id = ? AND user_id = ?', (due_time, task_id, user_id))
    conn.commit()
    conn.close()

def complete_task(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    completed_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('''
        UPDATE tasks SET is_done = 1, completed_date = ?
        WHERE id = ? AND user_id = ?
    ''', (completed_date, task_id, user_id))
    conn.commit()
    conn.close()

def delete_task(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
    conn.commit()
    conn.close()

def delete_completed_task(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM tasks WHERE id = ? AND user_id = ? AND is_done = 1', (task_id, user_id))
    conn.commit()
    conn.close()

def cleanup_old_completed_tasks():
    """Удаляет выполненные задачи старше 14 дней"""
    conn = sqlite3.connect('tasks.db')
    cur = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute('DELETE FROM tasks WHERE is_done = 1 AND completed_date < ?', (cutoff_date,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted