import asyncio
import logging
from automation.sandbox import run_in_sandbox

logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_code",
        "description": "Выполнить Python или Bash код в изолированной песочнице (Docker) и получить вывод. Используй для безопасного выполнения сложной логики, расчетов или парсинга.",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python", "bash"], "description": "Язык программирования (python или bash)"},
                "code": {"type": "string", "description": "Код для выполнения"}
            },
            "required": ["language", "code"]
        }
    }
}

async def execute(args: dict):
    language = args.get("language")
    code = args.get("code")
    
    if not language or not code:
        return "Ошибка: не указан language или code"
        
    try:
        logger.info(f"Запуск кода ({language}) в песочнице...")
        output = await run_in_sandbox(language, code)
        return output
    except Exception as e:
        return f"Ошибка выполнения в песочнице: {e}"
