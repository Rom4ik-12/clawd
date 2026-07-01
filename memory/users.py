import sqlite3
from config import DB_PATH, OWNER_ID

def get_user_role(user_id: int) -> str:
    if user_id == OWNER_ID:
        return 'owner'
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return row[0]
    return 'unknown'

def add_friend(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, role) VALUES (?, 'friend')", (user_id,))
    conn.commit()
    conn.close()

def is_allowed(user_id: int) -> bool:
    role = get_user_role(user_id)
    return role in ['owner', 'friend']
