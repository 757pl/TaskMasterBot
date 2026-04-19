import sqlite3

conn = sqlite3.connect('tasks.db')
cur = conn.cursor()

# Создаём таблицу заново с нужными колонками
cur.execute('''
CREATE TABLE IF NOT EXISTS tasks_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_text TEXT,
    due_date TEXT,
    due_time TEXT DEFAULT '07:00',
    completed_date TEXT,
    is_done INTEGER DEFAULT 0
)
''')

# Копируем старые данные (если есть)
cur.execute('''
INSERT INTO tasks_new (id, user_id, task_text, due_date, is_done)
SELECT id, user_id, task_text, due_date, is_done FROM tasks
''')

cur.execute('DROP TABLE tasks')
cur.execute('ALTER TABLE tasks_new RENAME TO tasks')

conn.commit()
conn.close()
print("✅ Таблица tasks обновлена с колонкой due_time")