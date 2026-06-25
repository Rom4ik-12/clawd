"""
llm/tools.py — OpenAI function definitions + локальное выполнение простых инструментов
"""
import re
import random
import datetime
import math
import pytz

# ─────────────────────────────────────────────────────────────────────────────
# OpenAI tools schema — передаётся в API как tools=AGENT_TOOLS
# ─────────────────────────────────────────────────────────────────────────────
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Поиск информации в интернете через SearXNG. Используй если нужно что-то найти или погуглить.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Выполнить bash-команду на хосте. Можно запускать python-скрипты, системные утилиты, смотреть процессы и т.д. Полный доступ без ограничений.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Команда для выполнения в bash"},
                    "timeout": {"type": "integer", "description": "Таймаут в секундах (по умолчанию 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Прочитать содержимое файла на хосте.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Абсолютный или относительный путь к файлу"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Записать или перезаписать файл на хосте.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "content": {"type": "string", "description": "Содержимое файла"},
                    "append": {"type": "boolean", "description": "Если true — дописать в конец файла (по умолчанию false)"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Заменить определенный фрагмент текста в существующем файле на новый.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "search_text": {"type": "string", "description": "Точный текст или блок, который нужно найти и заменить в файле"},
                    "replace_text": {"type": "string", "description": "Текст, на который нужно заменить найденный фрагмент"}
                },
                "required": ["path", "search_text", "replace_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Посмотреть список файлов и папок в директории на хосте.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к директории (по умолчанию текущая)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Получить информацию о системе: CPU, RAM, диск, uptime, Python, IP.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "Скачать файл по URL и сохранить на хост.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL файла для скачивания"},
                    "dest": {"type": "string", "description": "Путь для сохранения файла (опционально)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Отправить сообщение пользователю или в чат в Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Юзернейм (@username) или числовой ID"},
                    "text": {"type": "string", "description": "Текст сообщения"}
                },
                "required": ["username", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": "Отправить файл (документ, фото, видео) пользователю или в чат в Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Юзернейм (@username) или числовой ID (по умолчанию текущий чат)"},
                    "path": {"type": "string", "description": "Путь к файлу на сервере"},
                    "caption": {"type": "string", "description": "Подпись к файлу"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_poll",
            "description": "Создать и отправить опрос или викторину в Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Юзернейм (@username) или числовой ID (по умолчанию текущий чат)"},
                    "question": {"type": "string", "description": "Текст вопроса"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список вариантов ответов (от 2 до 10 вариантов)"
                    },
                    "is_anonymous": {"type": "boolean", "description": "Анонимный ли опрос (по умолчанию true)"},
                    "is_quiz": {"type": "boolean", "description": "Является ли опрос викториной с правильным ответом (по умолчанию false)"},
                    "correct_option_id": {"type": "integer", "description": "Индекс правильного ответа (0-indexed, требуется только если is_quiz=true)"}
                },
                "required": ["question", "options"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_location",
            "description": "Отправить геопозицию (локацию) в Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Юзернейм (@username) или числовой ID (по умолчанию текущий чат)"},
                    "latitude": {"type": "number", "description": "Широта (latitude), например 55.7558"},
                    "longitude": {"type": "number", "description": "Долгота (longitude), например 37.6173"}
                },
                "required": ["latitude", "longitude"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "join_channel",
            "description": "Подписаться на Telegram-канал или группу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Юзернейм (@channel) или ссылка https://t.me/channel"}
                },
                "required": ["channel"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sticker_set",
            "description": "Запустить полный анализ стикерпака в фоне (только для владельца). Если вызвана без параметров, пытается взять стикерпак из сообщения, на которое отвечает (reply).",
            "parameters": {
                "type": "object",
                "properties": {
                    "short_name": {"type": "string", "description": "Короткое имя стикерпака (short_name). Опционально."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leave_channel",
            "description": "Выйти из Telegram-канала или группы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Юзернейм (@channel) или ссылка"}
                },
                "required": ["channel"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_button",
            "description": "Нажать на кнопку в сообщении (inline/reply кнопки, капчи, верификации).",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Индекс кнопки (0, 1, 2...)"},
                    "text": {"type": "string", "description": "Текст кнопки (альтернатива индексу)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Запланировать отправку сообщения через N секунд.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer", "description": "Через сколько секунд"},
                    "text": {"type": "string", "description": "Текст сообщения"},
                    "target": {"type": "string", "description": "Кому отправить (@username или chat_id). По умолчанию в текущий чат."}
                },
                "required": ["seconds", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "react",
            "description": "Поставить реакцию эмодзи под сообщением.",
            "parameters": {
                "type": "object",
                "properties": {
                    "emoji": {"type": "string", "description": "Эмодзи для реакции, например 👍 🔥 ❤️ 💀"}
                },
                "required": ["emoji"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forward_messages",
            "description": "Переслать сообщения из одного чата в другой.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_chat": {"type": "string", "description": "ID чата или юзернейм источника (@username или id)."},
                    "message_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Список ID сообщений для пересылки."
                    },
                    "to_chat": {"type": "string", "description": "ID чата или юзернейм назначения. По умолчанию текущий чат."}
                },
                "required": ["from_chat", "message_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_feed",
            "description": "Прочитать свежие посты из подписанных Telegram-каналов.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_chat_messages",
            "description": "Прочитать последние сообщения из указанного Telegram-чата.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat": {"type": "string", "description": "Юзернейм, ссылка или ID чата"},
                    "limit": {"type": "integer", "description": "Сколько сообщений прочитать (по умолчанию 10)"}
                },
                "required": ["chat"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_profile",
            "description": "Изучить профиль пользователя, канала или группы в Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Юзернейм (@username), ID или ссылка"}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_telegram",
            "description": "Найти публичные или свои Telegram-каналы/группы/контакты, либо сообщения по теме/ключевым словам (аналог поисковой строки в самом Telegram).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "scope": {
                        "type": "string",
                        "enum": ["global", "local", "messages", "all"],
                        "description": "Область поиска: global (глобальный поиск публичных каналов/групп/пользователей), local (поиск среди личных диалогов/чатов), messages (поиск по тексту сообщений во всех чатах), all (глобальный + локальный)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_sticker",
            "description": "Отправить стикер из личной библиотеки. Используй когда момент эмоционально подходящий: что-то смешное, удивительное, грустное, победное, трогательное и т.д. Подбирает стикер по ключевым словам из собственной коллекции.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Ключевое слово или короткое описание нужной эмоции/ситуации, например: 'смех', 'победа', 'грусть', 'удивление', 'огонь', 'котик'"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "Вычислить математическое выражение.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Математическое выражение, например '2 + 2 * 10'"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Узнать текущее время.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "random_number",
            "description": "Получить случайное число в диапазоне.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min": {"type": "integer", "description": "Минимум"},
                    "max": {"type": "integer", "description": "Максимум"}
                },
                "required": ["min", "max"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Внутренние размышления — невидимы собеседнику. Используй для анализа ситуации перед ответом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thoughts": {"type": "string", "description": "Твои мысли и рассуждения"}
                },
                "required": ["thoughts"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Завершить кастомное задание и отправить владельцу финальный отчёт.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {"type": "string", "description": "Финальный отчёт для владельца"}
                },
                "required": ["report"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_schedule",
            "description": "Запланировать регулярное или разовое действие (например, отправку сообщения или сводки новостей) в планировщик.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "enum": ["send_message", "news_digest", "run_agent_task"],
                        "description": "Тип задачи: send_message (отправка сообщения), news_digest (новостная сводка из каналов), run_agent_task (запуск агентного ИИ-цикла для выполнения произвольного текстового поручения/инструкции)."
                    },
                    "target": {
                        "type": "string",
                        "description": "Куда присылать результат/сообщение (юзернейм, ID чата или имя получателя). По умолчанию в текущий чат."
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": ["once", "interval", "daily"],
                        "description": "Режим повтора: once (разово в указанную дату/время), interval (каждые N секунд), daily (каждый день в указанное время ЧЧ:ММ по Москве)."
                    },
                    "schedule_value": {
                        "type": "string",
                        "description": "Значение расписания. Для 'once': дата/время в формате 'ГГГГ-ММ-ДД ЧЧ:ММ:СС'. Для 'interval': число секунд. Для 'daily': время в формате 'ЧЧ:ММ' (по Москве)."
                    },
                    "payload": {
                        "type": "string",
                        "description": "Для send_message: текст сообщения. Для news_digest: список Telegram-каналов через запятую. Для run_agent_task: детальное текстовое поручение/задание для ИИ, которое он должен выполнить при наступлении времени."
                    }
                },
                "required": ["task_type", "schedule_type", "schedule_value", "payload"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_schedules",
            "description": "Посмотреть список всех активных запланированных задач из БД.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_schedule",
            "description": "Удалить/отменить запланированную задачу по её ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer", "description": "ID задачи из списка запланированных"}
                },
                "required": ["schedule_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Обновить настройки профиля юзербота (имя, био, юзернейм, аватар).",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "Имя"},
                    "last_name": {"type": "string", "description": "Фамилия"},
                    "about": {"type": "string", "description": "Описание профиля (био, о себе)"},
                    "username": {"type": "string", "description": "Новый юзернейм (без @)"},
                    "avatar_path": {"type": "string", "description": "Путь к файлу картинки на сервере или URL для скачивания и установки нового аватара"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_telethon_code",
            "description": "Выполнить произвольный асинхронный Python-код с доступом к клиенту Telethon (client) и событию (event). Возвращает значение переменной result или последнее выражение.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Асинхронный код на Python. Пример: 'result = await client.get_me()'"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_music",
            "description": "Отправить аудиофайл как музыкальный трек с указанием исполнителя и названия.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Получатель (@username, ID или ссылка). по умолчанию текущий чат."},
                    "path": {"type": "string", "description": "Путь к аудиофайлу на сервере"},
                    "title": {"type": "string", "description": "Название песни/трека"},
                    "performer": {"type": "string", "description": "Имя исполнителя"},
                    "caption": {"type": "string", "description": "Текст сообщения к аудиофайлу"}
                },
                "required": ["path", "title", "performer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_frames",
            "description": "Извлечь кадры из видеофайла для визуального анализа.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к видеофайлу на сервере"},
                    "count": {"type": "integer", "description": "Количество кадров для извлечения (по умолчанию 5)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_bot",
            "description": "Перезапустить процесс бота (применит все изменения в коде).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reload_skills",
            "description": "Перезагрузить динамические скиллы из папки skills.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Локальное выполнение простых инструментов (без Telegram и хоста)
# ─────────────────────────────────────────────────────────────────────────────
def execute_local_tool(name: str, args: dict):
    """Выполняет инструменты не требующие Telegram или хоста."""

    if name == "calc":
        try:
            expr = args.get("expression", "")
            safe_ns = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
            result = eval(expr, {"__builtins__": {}}, safe_ns)
            return str(result)
        except Exception as e:
            return f"ошибка вычисления: {e}"

    elif name == "get_time":
        from config import local_now
        return local_now().strftime("%H:%M %d.%m.%Y")

    elif name == "random_number":
        lo = args.get("min", 1)
        hi = args.get("max", 100)
        return str(random.randint(lo, hi))

    elif name == "think":
        thoughts = args.get("thoughts", "")
        if thoughts:
            import logging
            logging.getLogger("think").info(f"🧠 [think] {thoughts}")
        return "мысли зафиксированы"

    return None  # не локальный инструмент


import os
import importlib.util

DYNAMIC_SKILLS = {}

def load_dynamic_skills():
    global DYNAMIC_SKILLS
    skills_dir = "skills"
    if not os.path.exists(skills_dir):
        os.makedirs(skills_dir, exist_ok=True)
        return
        
    for filename in os.listdir(skills_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            skill_name = filename[:-3]
            path = os.path.join(skills_dir, filename)
            try:
                spec = importlib.util.spec_from_file_location(skill_name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "SCHEMA") and hasattr(mod, "execute"):
                    DYNAMIC_SKILLS[skill_name] = mod
                    # Check if already in AGENT_TOOLS
                    exists = any(t.get("function", {}).get("name") == skill_name for t in AGENT_TOOLS)
                    if not exists:
                        AGENT_TOOLS.append(mod.SCHEMA)
            except Exception as e:
                import logging
                logging.getLogger("tools").error(f"Error loading skill {skill_name}: {e}")

# Выполняем автозагрузку при импорте модуля
load_dynamic_skills()
