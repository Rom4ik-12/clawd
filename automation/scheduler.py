"""
automation/scheduler.py — Фоновые задачи агента с поддержкой динамического планировщика из БД
"""
import asyncio
import logging
import datetime
from zoneinfo import ZoneInfo
from config import local_now, OWNER_ID, TIMEZONE
from memory.sqlite import get_setting, set_setting, get_active_schedules, update_schedule_runs, delete_db_schedule
from llm.provider import generate_response

logger = logging.getLogger("scheduler")

# Каналы по умолчанию для чтения сводок новостей
DEFAULT_NEWS_CHANNELS = [
    "pvxblog",
    "telelakel",
    "techmedia",
    "yep_news",
    "whackdoor"
]

async def generate_daily_news_digest_for_payload(client, payload: str) -> str:
    """Собирает посты из указанных в payload (через запятую) каналов и генерирует сводку."""
    channels = [c.strip() for c in payload.split(",") if c.strip()]
    if not channels:
        return "Каналы для сводки не указаны."
        
    posts_data = []
    day_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    
    for channel in channels:
        try:
            target = channel.replace("https://t.me/", "").replace("@", "").strip()
            entity = await client.get_entity(target)
            
            try:
                from telethon.tl.functions.channels import JoinChannelRequest
                await client(JoinChannelRequest(entity))
            except Exception:
                pass
                
            messages = await client.get_messages(entity, limit=10)
            channel_posts = []
            for msg in messages:
                if msg.date > day_ago and msg.text:
                    channel_posts.append(msg.text.strip())
            
            if channel_posts:
                posts_text = "\n---\n".join(channel_posts[:3])
                posts_data.append(f"Канал @{target}:\n{posts_text}")
        except Exception as e:
            logger.warning(f"Failed to fetch posts from {channel}: {e}")

    if not posts_data:
        return "Сводка новостей: За последние 24 часа новых постов в отслеживаемых IT-каналах не найдено."

    combined_posts = "\n\n====================\n\n".join(posts_data)
    prompt = (
        "Ты — Claw'd, ИИ-ассистент. Составь для своего владельца краткую и структурированную новостную сводку "
        "за последние 24 часа на основе следующих публикаций из Telegram-каналов:\n\n"
        f"{combined_posts}\n\n"
        "Сделай сводку лаконичной, выдели ключевые моменты. Пиши строго на русском языке, без использования смайлов и эмодзи."
    )

    try:
        digest = await generate_response(prompt, temperature=0.7)
        return digest
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return f"Ошибка при генерации сводки: {e}"

async def generate_daily_news_digest(client) -> str:
    """Фолбэк-генерация сводки по умолчанию."""
    channels_str = get_setting("news_channels", ",".join(DEFAULT_NEWS_CHANNELS))
    return await generate_daily_news_digest_for_payload(client, channels_str)

async def execute_task(client, task_type: str, target: str, payload: str):
    """Выполняет задачу по её типу."""
    try:
        # Пытаемся распарсить целевой ID (если это число)
        try:
            peer = int(target)
        except ValueError:
            peer = target
            
        if task_type == "send_message":
            await client.send_message(peer, payload)
            logger.info(f"Successfully sent scheduled message to {target}")
            
        elif task_type == "news_digest":
            digest = await generate_daily_news_digest_for_payload(client, payload)
            await client.send_message(peer, digest)
            logger.info(f"Successfully sent scheduled news digest to {target}")

        elif task_type == "run_agent_task":
            from brain.think import run_scheduled_agent_task
            await run_scheduled_agent_task(client, target, payload)
            logger.info(f"Successfully ran scheduled agent task for {target}")
            
    except Exception as e:
        logger.error(f"Error executing task {task_type} for {target}: {e}")

async def background_routine(client=None):
    """Фоновые задачи: авто-сводки, динамические шедулеры и т.д."""
    logger.info("⏰ [Scheduler] Фоновые задачи запущены")
    
    if client is None:
        from tg.client import get_client
        client = get_client()

    last_summary_date = None

    while True:
        try:
            now = local_now()
            
            # 1. Ежедневная дефолтная сводка в 12:00 по МСК (резервная)
            if now.hour == 12 and now.minute == 0 and last_summary_date != now.date():
                logger.info("📊 [Scheduler] Время ежедневной сводки новостей!")
                last_summary_date = now.date()
                # Проверим, если в динамических задачах уже есть ежедневная сводка, не шлем дубликат
                active_schedules = get_active_schedules()
                has_news_digest_schedule = any(s[1] == 'news_digest' and s[4] == 'daily' for s in active_schedules)
                if not has_news_digest_schedule:
                    digest = await generate_daily_news_digest(client)
                    await client.send_message(OWNER_ID, digest)
                    logger.info("✅ [Scheduler] Дефолтная сводка отправлена владельцу")
            
            # 2. Выполнение динамических задач из БД
            schedules = get_active_schedules()
            for s in schedules:
                sid, ttype, target, payload, stype, sval, lrun, nrun = s
                
                if not nrun:
                    continue
                    
                # Парсим next_run из isoformat
                next_run_dt = datetime.datetime.fromisoformat(nrun)
                
                if now >= next_run_dt:
                    logger.info(f"🚀 Running scheduled task ID {sid} ({ttype})")
                    # Выполняем задачу асинхронно, чтобы не блокировать цикл
                    asyncio.create_task(execute_task(client, ttype, target, payload))
                    
                    # Расчет следующего запуска
                    last_run_str = now.isoformat()
                    next_run_str = None
                    
                    if stype == "once":
                        # Разовая задача удаляется/деактивируется
                        delete_db_schedule(sid)
                        continue
                        
                    elif stype == "interval":
                        try:
                            seconds = int(sval)
                            next_run_str = (now + datetime.timedelta(seconds=seconds)).isoformat()
                        except ValueError:
                            delete_db_schedule(sid)
                            continue
                            
                    elif stype == "daily":
                        try:
                            hm = datetime.datetime.strptime(sval, "%H:%M").time()
                            # Прибавляем 1 день к текущему запланированному времени
                            next_run_dt = next_run_dt + datetime.timedelta(days=1)
                            # На всякий случай проверяем, чтобы дата была в будущем
                            if next_run_dt <= now:
                                next_run_dt = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0) + datetime.timedelta(days=1)
                            next_run_str = next_run_dt.isoformat()
                        except Exception:
                            delete_db_schedule(sid)
                            continue
                            
                    update_schedule_runs(sid, last_run_str, next_run_str)
                    
        except Exception as e:
            logger.error(f"[Scheduler] Ошибка в планировщике: {e}")
            
        await asyncio.sleep(20)
