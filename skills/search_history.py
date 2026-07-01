import logging
from config import DB_PATH
import sqlite3

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_history",
        "description": "Искать информацию (RAG) в истории сообщений и памяти бота по ключевым словам. Используй это, когда пользователь спрашивает о чем-то из прошлого или из каналов.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
                "limit": {"type": "integer", "description": "Количество результатов (максимум 10)"}
            },
            "required": ["query"]
        }
    }
}

async def execute(args: dict):
    query = args.get("query")
    limit = args.get("limit", 5)
    
    if not query:
        return "Ошибка: пустой запрос."
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Простой FTS поиск по таблице сообщений, если она существует
        # Для начала ищем просто LIKE в short_memory (как пример)
        cursor.execute('''
            SELECT id, role, content, timestamp 
            FROM short_memory 
            WHERE content LIKE ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (f'%{query}%', limit))
        
        results = cursor.fetchall()
        
        if not results:
            return "Ничего не найдено в памяти по этому запросу."
            
        formatted = "Найденные записи в памяти:\n"
        for r in results:
            formatted += f"[{r['timestamp']}] {r['role']}: {r['content'][:100]}...\n"
            
        return formatted
        
    except Exception as e:
        logger.error(f"Search history error: {e}")
        return f"Ошибка при поиске: {e}"
