# Database for SHORT and FACT memory
import sqlite3
from config import DB_PATH, OWNER_ID

MAX_MESSAGES_PER_CHAT = 300


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY, chat_id INTEGER, sender_id INTEGER,
                  text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS facts
                 (id INTEGER PRIMARY KEY, user_id INTEGER, fact TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS summaries
                 (id INTEGER PRIMARY KEY, chat_id INTEGER, summary TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS activity_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, activity_type TEXT,
                  description TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS stickers
                 (id INTEGER PRIMARY KEY, file_id TEXT UNIQUE, description TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS shell_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  command TEXT,
                  result TEXT,
                  exit_code INTEGER,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS schedules
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_type TEXT,
                  target TEXT,
                  payload TEXT,
                  schedule_type TEXT,
                  schedule_value TEXT,
                  last_run DATETIME,
                  next_run DATETIME,
                  active INTEGER DEFAULT 1)''')

    # Индексы
    c.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')

    conn.commit()
    conn.close()


def save_message(chat_id, sender_id, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (chat_id, sender_id, text) VALUES (?, ?, ?)",
              (chat_id, sender_id, text))
    conn.commit()
    # Автоочистка
    c.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,))
    count = c.fetchone()[0]
    if count > MAX_MESSAGES_PER_CHAT:
        trim = count - MAX_MESSAGES_PER_CHAT
        c.execute("""
            DELETE FROM messages WHERE id IN (
                SELECT id FROM messages WHERE chat_id = ?
                ORDER BY timestamp ASC LIMIT ?
            )
        """, (chat_id, trim))
        conn.commit()
    conn.close()


def get_short_memory(chat_id, limit=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT text FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
              (chat_id, limit))
    msgs = c.fetchall()
    conn.close()
    return [m[0] for m in msgs][::-1]


def save_summary(chat_id, summary_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM summaries WHERE chat_id = ?", (chat_id,))
    count = c.fetchone()[0]
    if count >= 5:
        c.execute("""
            DELETE FROM summaries WHERE id IN (
                SELECT id FROM summaries WHERE chat_id = ?
                ORDER BY timestamp ASC LIMIT ?
            )
        """, (chat_id, count - 4))
    c.execute("INSERT INTO summaries (chat_id, summary) VALUES (?, ?)", (chat_id, summary_text))
    conn.commit()
    conn.close()


def get_summaries(chat_id, limit=3):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT summary FROM summaries WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
              (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows][::-1]


def save_fact(user_id, fact):
    if not fact or not fact.strip():
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM facts WHERE user_id = ? AND fact = ?", (user_id, fact.strip()))
    c.execute("INSERT INTO facts (user_id, fact, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
              (user_id, fact.strip()))
    conn.commit()
    conn.close()


def get_facts(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fact FROM facts WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows][::-1]


def get_active_contacts(limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT chat_id, text, MAX(timestamp) as last_ts
        FROM messages
        WHERE chat_id != ? AND chat_id > 0
        GROUP BY chat_id
        ORDER BY last_ts DESC
        LIMIT ?
    """, (OWNER_ID, limit))
    contacts = c.fetchall()
    conn.close()
    return contacts


def clear_chat_context(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        c.execute("DELETE FROM summaries WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка очистки контекста {chat_id}: {e}")
        return False
    finally:
        conn.close()


def clear_chat_summaries(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM summaries WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка очистки саммари {chat_id}: {e}")
        return False
    finally:
        conn.close()


def clear_chat_messages(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка очистки сообщений {chat_id}: {e}")
        return False
    finally:
        conn.close()


def save_sticker(file_id, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO stickers (file_id, description) VALUES (?, ?)",
                  (file_id, description))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения стикера: {e}")
    finally:
        conn.close()


def delete_sticker(description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM stickers WHERE description = ?", (description,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка удаления стикера: {e}")
        return False
    finally:
        conn.close()


def get_all_stickers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT description FROM stickers ORDER BY description")
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_matching_sticker(query):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id FROM stickers WHERE description LIKE ? ORDER BY RANDOM() LIMIT 1",
              (f"%{query}%",))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def log_activity(activity_type, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO activity_log (activity_type, description) VALUES (?, ?)",
                  (activity_type, description))
        conn.commit()
    except Exception as e:
        print(f"Ошибка лога активности: {e}")
    finally:
        conn.close()


def log_shell(command, result, exit_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO shell_history (command, result, exit_code) VALUES (?, ?, ?)",
                  (command, result[:2000], exit_code))
        conn.commit()
    except Exception as e:
        print(f"Ошибка лога shell: {e}")
    finally:
        conn.close()


def get_shell_history(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT command, result, exit_code, timestamp FROM shell_history ORDER BY timestamp DESC LIMIT ?",
              (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_setting(key: str, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else default
    except Exception:
        return default
    finally:
        conn.close()


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения настройки: {e}")
    finally:
        conn.close()


def get_today_activities():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT activity_type, description, timestamp FROM activity_log
                 WHERE timestamp >= datetime('now', '-24 hours') ORDER BY timestamp ASC""")
    rows = c.fetchall()
    conn.close()
    return rows


def add_db_schedule(task_type, target, payload, schedule_type, schedule_value, next_run):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO schedules (task_type, target, payload, schedule_type, schedule_value, next_run)
                     VALUES (?, ?, ?, ?, ?, ?)""", (task_type, target, payload, schedule_type, schedule_value, next_run))
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()


def get_active_schedules():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT id, task_type, target, payload, schedule_type, schedule_value, last_run, next_run FROM schedules WHERE active = 1")
        return c.fetchall()
    finally:
        conn.close()


def update_schedule_runs(schedule_id, last_run, next_run):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("UPDATE schedules SET last_run = ?, next_run = ? WHERE id = ?", (last_run, next_run, schedule_id))
        conn.commit()
    finally:
        conn.close()


def delete_db_schedule(schedule_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()
