"""
tg/panel.py — Бот-панель управления Clawd
"""
import asyncio
import time
import os
import logging
import sqlite3
from telethon import TelegramClient, events, Button
from config import API_ID, API_HASH, PANEL_BOT_TOKEN, OWNER_ID, OWNER_NAME, DB_PATH
from memory.sqlite import (
    get_today_activities, clear_chat_context, get_setting, set_setting,
    get_shell_history
)

logger = logging.getLogger("panel")

ALLOWED_USERS = {OWNER_ID}

_bot_client = None


def init_panel_bot(main_client):
    global _bot_client
    if not PANEL_BOT_TOKEN:
        logger.warning("[Panel] PANEL_BOT_TOKEN не настроен — панель не запущена")
        return None

    _bot_client = TelegramClient("panel_bot_session", API_ID, API_HASH)

    from automation.owner_alert import set_alert_bot
    set_alert_bot(_bot_client)

    setup_handlers(_bot_client, main_client)
    asyncio.create_task(_bot_client.start(bot_token=PANEL_BOT_TOKEN))
    logger.info("[Panel] Панель управления запущена!")
    return _bot_client


# Состояния ввода
_waiting_clear_context = {}
_waiting_mem_view_msgs = {}
_waiting_mem_view_sums = {}
_waiting_mem_gen_sum = {}
_waiting_mem_clear_all = {}
_waiting_mem_clear_msgs = {}
_waiting_mem_clear_sums = {}
_waiting_sticker_file = {}
_waiting_sticker_desc = {}
_waiting_sticker_delete = {}
_waiting_shell_cmd = {}
_waiting_name = {}
_waiting_bio = {}
_waiting_username = {}
_waiting_avatar = {}
_waiting_timezone = {}
_waiting_add_schedule = {}
_waiting_delete_schedule = {}
_waiting_bot_name = {}
_waiting_add_trigger = {}
_waiting_delete_trigger = {}


def setup_handlers(bot, main_client):
    from tg.state import get_action

    def main_menu():
        bot_name = get_setting("bot_name", "Claw'd")
        text = (
            f"{bot_name} - Панель управления\n\n"
            f"Статус: {get_action()}\n\n"
            f"Управляй агентом через кнопки ниже:"
        )
        markup = [
            [Button.inline("Системный статус", b"sys_status")],
            [Button.inline("Выполнить команду", b"shell_cmd"),
             Button.inline("История команд", b"shell_history")],
            [Button.inline("Память и Саммари", b"mem_menu"),
             Button.inline("База стикеров", b"sticker_menu")],
            [Button.inline("Настройки", b"settings_menu")],
        ]
        return text, markup

    @bot.on(events.NewMessage(pattern="/start"))
    async def start_handler(event):
        if event.sender_id not in ALLOWED_USERS:
            return
        _clear_state(event.sender_id)
        text, markup = main_menu()
        await event.respond(text, buttons=markup)

    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        if event.sender_id not in ALLOWED_USERS:
            await event.answer("Нет доступа", alert=True)
            return

        data = event.data

        if data == b"main_menu":
            _clear_state(event.sender_id)
            text, markup = main_menu()
            await event.edit(text, buttons=markup)
            await event.answer()

        elif data == b"sys_status":
            await event.answer("Собираю статус...")
            status = await _get_system_status(main_client)
            await event.respond(status, buttons=[[Button.inline("Назад", b"main_menu")]])

        elif data == b"shell_cmd":
            _clear_state(event.sender_id)
            _waiting_shell_cmd[event.sender_id] = True
            await event.edit(
                "Выполнить команду\n\n"
                "Отправь bash-команду для выполнения на сервере.\n"
                "Примеры: ps aux | head -20, df -h, python3 -V",
                buttons=[[Button.inline("Отмена", b"main_menu")]]
            )
            await event.answer()

        elif data == b"shell_history":
            rows = get_shell_history(limit=10)
            if not rows:
                text = "История команд пуста"
            else:
                lines = []
                for cmd, result, exit_code, ts in rows:
                    status_text = "[OK]" if exit_code == 0 else "[ERROR]"
                    result_short = (result or "")[:100]
                    lines.append(f"{status_text} {cmd}\n-> {result_short}")
                text = "Последние 10 команд:\n\n" + "\n\n".join(lines)
            await event.respond(text, buttons=[[Button.inline("Назад", b"main_menu")]])
            await event.answer()

        elif data == b"clear_context" or data == b"mem_menu":
            _clear_state(event.sender_id)
            text = (
                "Управление памятью чатов\n\n"
                "Выбери действие для просмотра или очистки истории сообщений и саммари:"
            )
            markup = [
                [Button.inline("Просмотр сообщений (История)", b"mem_view_msgs")],
                [Button.inline("Просмотр саммари", b"mem_view_sums")],
                [Button.inline("Сгенерировать саммари сейчас", b"mem_gen_sum")],
                [Button.inline("Очистить ВСЁ (сообщения + саммари)", b"mem_clear_all")],
                [Button.inline("Удалить только сообщения", b"mem_clear_msgs")],
                [Button.inline("Удалить только саммари", b"mem_clear_sums")],
                [Button.inline("Назад в меню", b"main_menu")]
            ]
            await event.edit(text, buttons=markup)
            await event.answer()

        elif data == b"mem_view_msgs":
            _clear_state(event.sender_id)
            _waiting_mem_view_msgs[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку на человека/группу для просмотра истории сообщений:", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"mem_view_sums":
            _clear_state(event.sender_id)
            _waiting_mem_view_sums[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку для просмотра саммари:", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"mem_gen_sum":
            _clear_state(event.sender_id)
            _waiting_mem_gen_sum[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку для принудительной генерации саммари:", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"mem_clear_all":
            _clear_state(event.sender_id)
            _waiting_mem_clear_all[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку для полного удаления всей памяти (сообщения + саммари):", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"mem_clear_msgs":
            _clear_state(event.sender_id)
            _waiting_mem_clear_msgs[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку для удаления только истории сообщений чата:", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"mem_clear_sums":
            _clear_state(event.sender_id)
            _waiting_mem_clear_sums[event.sender_id] = True
            await event.edit("Отправь ID чата, @username или ссылку для удаления только саммари чата:", buttons=[[Button.inline("Отмена", b"mem_menu")]])
            await event.answer()

        elif data == b"sticker_menu":
            _clear_state(event.sender_id)
            text = (
                "Управление базой стикеров\n\n"
                "Выбери действие для просмотра, добавления или удаления стикеров:"
            )
            markup = [
                [Button.inline("Просмотр стикеров", b"sticker_view")],
                [Button.inline("Добавить стикер", b"sticker_add")],
                [Button.inline("Удалить стикер", b"sticker_delete")],
                [Button.inline("Назад в меню", b"main_menu")]
            ]
            await event.edit(text, buttons=markup)
            await event.answer()

        elif data == b"sticker_view":
            from memory.sqlite import get_all_stickers
            stickers = get_all_stickers()
            if not stickers:
                text = "База стикеров пуста."
            else:
                text = "Доступные стикеры в базе (ключевые слова):\n\n" + "\n".join(f"- {s}" for s in stickers)
            await event.respond(text, buttons=[[Button.inline("Назад", b"sticker_menu")]])
            await event.answer()

        elif data == b"sticker_add":
            _clear_state(event.sender_id)
            _waiting_sticker_file[event.sender_id] = True
            await event.edit("Отправь стикер, который хочешь добавить в базу:", buttons=[[Button.inline("Отмена", b"sticker_menu")]])
            await event.answer()

        elif data == b"sticker_delete":
            _clear_state(event.sender_id)
            _waiting_sticker_delete[event.sender_id] = True
            await event.edit("Отправь ключевое слово стикера, который хочешь удалить из базы:", buttons=[[Button.inline("Отмена", b"sticker_menu")]])
            await event.answer()

        elif data == b"settings_menu":
            await _show_settings_menu(bot, event.chat_id, event)
            await event.answer()

        elif data == b"set_name":
            _clear_state(event.sender_id)
            _waiting_name[event.sender_id] = True
            await event.edit(
                "Изменение имени\n\n"
                "Отправь новое имя для аккаунта. Можно указать имя и фамилию через пробел (например: Имя Фамилия):",
                buttons=[[Button.inline("Отмена", b"settings_menu")]]
            )
            await event.answer()

        elif data == b"set_bio":
            _clear_state(event.sender_id)
            _waiting_bio[event.sender_id] = True
            await event.edit(
                "Изменение описания (\"О себе\")\n\n"
                "Отправь новое описание для аккаунта (максимум 70 символов):\n"
                "Отправьте - чтобы удалить описание.",
                buttons=[[Button.inline("Отмена", b"settings_menu")]]
            )
            await event.answer()

        elif data == b"set_avatar":
            _clear_state(event.sender_id)
            _waiting_avatar[event.sender_id] = True
            await event.edit(
                "Изменение аватара\n\n"
                "Отправь фотографию (сжатым фото или файлом), которую хочешь установить на аватар:",
                buttons=[[Button.inline("Отмена", b"settings_menu")]]
            )
            await event.answer()

        elif data == b"set_username":
            _clear_state(event.sender_id)
            _waiting_username[event.sender_id] = True
            await event.edit(
                "Изменение юзернейма\n\n"
                "Отправь новый юзернейм (без @, минимум 5 символов):\n"
                "Отправьте - чтобы удалить юзернейм.",
                buttons=[[Button.inline("Отмена", b"settings_menu")]]
            )
            await event.answer()

        elif data == b"profile_settings":
            await _show_profile_settings(bot, event.chat_id, event)
            await event.answer()

        elif data == b"bot_config_menu":
            await _show_bot_config_menu(bot, event.chat_id, event)
            await event.answer()

        elif data == b"select_model_menu":
            await _show_select_model_menu(bot, event.chat_id, event)
            await event.answer()

        elif data.startswith(b"set_model_"):
            model_key = data.decode()[len("set_model_"):]
            model_map = {
                "gpt55": "codexsale/gpt-5.5",
                "gpt54": "codexsale/gpt-5.4",
                "gpt4o": "codexsale/gpt-4o",
                "claude35": "codexsale/claude-3-5-sonnet",
                "gemini2": "google/gemini-2.0-flash-exp:free"
            }
            selected_model = model_map.get(model_key, "codexsale/gpt-5.5")
            set_setting("primary_model", selected_model)
            await event.answer(f"Модель {selected_model} выбрана основной!", alert=True)
            await _show_bot_config_menu(bot, event.chat_id, event)

        elif data == b"set_timezone_start":
            _clear_state(event.sender_id)
            _waiting_timezone[event.sender_id] = True
            await event.edit(
                "Изменение часового пояса\n\n"
                "Отправьте имя часового пояса (например, Europe/Moscow, Europe/Paris, Asia/Tashkent):",
                buttons=[[Button.inline("Отмена", b"bot_config_menu")]]
            )
            await event.answer()

        elif data == b"set_bot_name_start":
            _clear_state(event.sender_id)
            _waiting_bot_name[event.sender_id] = True
            await event.edit(
                "Изменение имени бота (в prompt)\n\n"
                "Отправьте новое системное имя для бота (например, Claw'd):",
                buttons=[[Button.inline("Отмена", b"bot_config_menu")]]
            )
            await event.answer()

        elif data == b"triggers_menu":
            await _show_triggers_menu(bot, event.chat_id, event)
            await event.answer()

        elif data == b"add_trigger_start":
            _clear_state(event.sender_id)
            _waiting_add_trigger[event.sender_id] = True
            await event.edit(
                "Добавление триггера\n\n"
                "Отправьте ключевое слово или фразу, которую хотите добавить в качестве триггера в группах:",
                buttons=[[Button.inline("Отмена", b"triggers_menu")]]
            )
            await event.answer()

        elif data == b"delete_trigger_start":
            _clear_state(event.sender_id)
            _waiting_delete_trigger[event.sender_id] = True
            await event.edit(
                "Удаление триггера\n\n"
                "Отправьте номер триггера из списка или сам текст триггера, который хотите удалить:",
                buttons=[[Button.inline("Отмена", b"triggers_menu")]]
            )
            await event.answer()

        elif data == b"set_bot_lang_menu":
            await _show_select_lang_menu(bot, event.chat_id, event)
            await event.answer()

        elif data == b"set_lang_ru":
            set_setting("bot_language", "ru")
            await event.answer("Язык общения изменен на русский (ru)!", alert=True)
            await _show_bot_config_menu(bot, event.chat_id, event)

        elif data == b"set_lang_en":
            set_setting("bot_language", "en")
            await event.answer("Language changed to English (en)!", alert=True)
            await _show_bot_config_menu(bot, event.chat_id, event)

        elif data == b"schedulers_menu":
            await _show_schedulers_menu(bot, event.chat_id, event)
            await event.answer()

        elif data == b"add_sched_start":
            _clear_state(event.sender_id)
            _waiting_add_schedule[event.sender_id] = True
            await event.edit(
                "Добавление задачи в планировщик\n\n"
                "Отправьте сообщение со следующими параметрами, разделенными вертикальной чертой |\n\n"
                "тип_задачи | получатель | тип_повтора | значение | полезная_нагрузка\n\n"
                "Доступные типы задач:\n"
                "- send_message (отправка текста)\n"
                "- news_digest (сводка новостей из каналов)\n"
                "- run_agent_task (запуск мыслительного цикла ИИ)\n\n"
                "Типы повтора:\n"
                "- once (разово; значение: ГГГГ-ММ-ДД ЧЧ:ММ)\n"
                "- interval (интервал; значение: секунды, например 3600)\n"
                "- daily (ежедневно; значение: время ЧЧ:ММ)\n\n"
                "Примеры:\n"
                "send_message | @username | interval | 60 | Привет каждые 60с\n"
                "news_digest | @username | daily | 12:00 | pvxblog,techmedia\n"
                "run_agent_task | @username | once | 2026-06-19 14:00 | Проверь состояние сервера и напиши отчет\n\n"
                "Жду сообщение с задачей...",
                buttons=[[Button.inline("Отмена", b"schedulers_menu")]]
            )
            await event.answer()

        elif data == b"delete_sched_start":
            _clear_state(event.sender_id)
            _waiting_delete_schedule[event.sender_id] = True
            await event.edit(
                "Удаление задачи из планировщика\n\n"
                "Отправьте ID задачи, которую вы хотите удалить:",
                buttons=[[Button.inline("Отмена", b"schedulers_menu")]]
            )
            await event.answer()

    @bot.on(events.NewMessage)
    async def input_handler(event):
        if event.sender_id not in ALLOWED_USERS:
            return
        if event.message.text and event.message.text.startswith('/'):
            return

        # Изменение имени
        if _waiting_name.get(event.sender_id):
            name_text = (event.message.text or "").strip()
            if not name_text:
                return
            _waiting_name.pop(event.sender_id, None)
            
            parts = name_text.split(maxsplit=1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
            
            await event.respond("Обновляю имя...")
            try:
                from telethon.tl.functions.account import UpdateProfileRequest
                await main_client(UpdateProfileRequest(first_name=first_name, last_name=last_name))
                await event.respond("Имя успешно обновлено!")
            except Exception as e:
                await event.respond(f"Ошибка обновления имени: {e}")
                
            await _show_settings_menu(bot, event.chat_id)
            return

        # Изменение био
        if _waiting_bio.get(event.sender_id):
            bio_text = (event.message.text or "").strip()
            if not bio_text:
                return
            _waiting_bio.pop(event.sender_id, None)
            
            if bio_text == "-":
                bio_text = ""
                
            await event.respond("Обновляю описание...")
            try:
                from telethon.tl.functions.account import UpdateProfileRequest
                await main_client(UpdateProfileRequest(about=bio_text))
                await event.respond("Описание успешно обновлено!")
            except Exception as e:
                await event.respond(f"Ошибка обновления описания: {e}")
                
            await _show_settings_menu(bot, event.chat_id)
            return

        # Изменение юзернейма
        if _waiting_username.get(event.sender_id):
            username_text = (event.message.text or "").strip()
            if not username_text:
                return
            _waiting_username.pop(event.sender_id, None)
            
            if username_text == "-":
                username_text = ""
                
            await event.respond("Обновляю юзернейм...")
            try:
                from telethon.tl.functions.account import UpdateUsernameRequest
                await main_client(UpdateUsernameRequest(username=username_text))
                if username_text:
                    await event.respond(f"Юзернейм успешно изменен на @{username_text}!")
                else:
                    await event.respond("Юзернейм успешно удален!")
            except Exception as e:
                await event.respond(f"Ошибка обновления юзернейма: {e}")
                
            await _show_settings_menu(bot, event.chat_id)
            return

        # Изменение аватара
        if _waiting_avatar.get(event.sender_id):
            if not (event.message.photo or event.message.document):
                await event.respond("Пожалуйста, отправьте изображение (фото или файл).")
                return
                
            _waiting_avatar.pop(event.sender_id, None)
            await event.respond("Загружаю и устанавливаю новый аватар...")
            
            try:
                path = await event.message.download_media()
                if not path or not os.path.exists(path):
                    raise Exception("Не удалось скачать файл.")
                
                from telethon.tl.functions.photos import UploadProfilePhotoRequest
                uploaded = await main_client.upload_file(path)
                await main_client(UploadProfilePhotoRequest(fallback=False, file=uploaded))
                
                if os.path.exists(path):
                    os.remove(path)
                    
                await event.respond("Аватар успешно обновлен!")
            except Exception as e:
                await event.respond(f"Ошибка обновления аватара: {e}")
                
            await _show_settings_menu(bot, event.chat_id)
            return

        # Изменение часового пояса
        if _waiting_timezone.get(event.sender_id):
            tz_text = (event.message.text or "").strip()
            if not tz_text:
                return
            _waiting_timezone.pop(event.sender_id, None)
            
            from zoneinfo import ZoneInfo
            try:
                ZoneInfo(tz_text)
                set_setting("timezone", tz_text)
                await event.respond(f"Часовой пояс успешно изменен на {tz_text}!")
            except Exception as e:
                await event.respond(f"Ошибка: Неверное имя часового пояса ({e})")
                
            await _show_bot_config_menu(bot, event.chat_id)
            return

        # Изменение имени бота (в prompt)
        if _waiting_bot_name.get(event.sender_id):
            name_text = (event.message.text or "").strip()
            if not name_text:
                return
            _waiting_bot_name.pop(event.sender_id, None)
            set_setting("bot_name", name_text)
            await event.respond(f"Имя бота успешно изменено на {name_text}!")
            await _show_bot_config_menu(bot, event.chat_id)
            return

        # Добавление триггера
        if _waiting_add_trigger.get(event.sender_id):
            trigger_text = (event.message.text or "").strip()
            if not trigger_text:
                return
            _waiting_add_trigger.pop(event.sender_id, None)
            
            bot_trigger = get_setting("bot_trigger", "Claw'd")
            triggers = [t.strip() for t in bot_trigger.split(",") if t.strip()]
            if trigger_text not in triggers:
                triggers.append(trigger_text)
                set_setting("bot_trigger", ", ".join(triggers))
                await event.respond(f"Триггер {trigger_text} успешно добавлен!")
            else:
                await event.respond(f"Триггер {trigger_text} уже существует.")
                
            await _show_triggers_menu(bot, event.chat_id)
            return

        # Удаление триггера
        if _waiting_delete_trigger.get(event.sender_id):
            del_text = (event.message.text or "").strip()
            if not del_text:
                return
            _waiting_delete_trigger.pop(event.sender_id, None)
            
            bot_trigger = get_setting("bot_trigger", "Claw'd")
            triggers = [t.strip() for t in bot_trigger.split(",") if t.strip()]
            
            removed = False
            # Пробуем по номеру
            if del_text.isdigit():
                idx = int(del_text) - 1
                if 0 <= idx < len(triggers):
                    val = triggers.pop(idx)
                    removed = True
                    await event.respond(f"Триггер {val} успешно удален!")
            
            # Пробуем по точному совпадению текста
            if not removed:
                if del_text in triggers:
                    triggers.remove(del_text)
                    removed = True
                    await event.respond(f"Триггер {del_text} успешно удален!")
                    
            if removed:
                set_setting("bot_trigger", ", ".join(triggers))
            else:
                await event.respond(f"Триггер {del_text} не найден в списке.")
                
            await _show_triggers_menu(bot, event.chat_id)
            return

        # Добавление задачи в планировщик
        if _waiting_add_schedule.get(event.sender_id):
            sched_text = (event.message.text or "").strip()
            if not sched_text:
                return
            _waiting_add_schedule.pop(event.sender_id, None)
            
            parts = [p.strip() for p in sched_text.split("|")]
            if len(parts) < 5:
                await event.respond("Ошибка: неверный формат. Нужно передать все 5 параметров через |.")
                await _show_schedulers_menu(bot, event.chat_id)
                return
                
            task_type, target, schedule_type, schedule_value, payload = parts
            
            try:
                from config import local_now
                import datetime
                now = local_now()
                next_run = None

                if schedule_type == "once":
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                        try:
                            dt = datetime.datetime.strptime(schedule_value, fmt)
                            from zoneinfo import ZoneInfo
                            from config import TIMEZONE
                            next_run_dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
                            next_run = next_run_dt.isoformat()
                            break
                        except ValueError:
                            continue
                    if not next_run:
                        raise ValueError("Неверный формат даты. Используй 'YYYY-MM-DD HH:MM:SS'.")

                elif schedule_type == "interval":
                    seconds = int(schedule_value)
                    next_run = (now + datetime.timedelta(seconds=seconds)).isoformat()

                elif schedule_type == "daily":
                    hm = datetime.datetime.strptime(schedule_value, "%H:%M").time()
                    target_dt = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
                    if target_dt <= now:
                        target_dt += datetime.timedelta(days=1)
                    next_run = target_dt.isoformat()

                from memory.sqlite import add_db_schedule
                sched_id = add_db_schedule(task_type, target, payload, schedule_type, schedule_value, next_run)
                await event.respond(f"Задача успешно добавлена в расписание!\nID: {sched_id}\nСледующий запуск: {next_run}")
            except Exception as e:
                await event.respond(f"Ошибка добавления задачи: {e}")
                
            await _show_schedulers_menu(bot, event.chat_id)
            return

        # Удаление задачи из планировщика
        if _waiting_delete_schedule.get(event.sender_id):
            del_text = (event.message.text or "").strip()
            if not del_text or not del_text.isdigit():
                await event.respond("Пожалуйста, введите корректный числовой ID.")
                return
            _waiting_delete_schedule.pop(event.sender_id, None)
            
            try:
                from memory.sqlite import delete_db_schedule
                success = delete_db_schedule(int(del_text))
                if success:
                    await event.respond(f"Задача с ID {del_text} успешно удалена.")
                else:
                    await event.respond(f"Задача с ID {del_text} не найдена.")
            except Exception as e:
                await event.respond(f"Ошибка: {e}")
                
            await _show_schedulers_menu(bot, event.chat_id)
            return

        # Выполнение shell-команды
        if _waiting_shell_cmd.get(event.sender_id):
            _waiting_shell_cmd.pop(event.sender_id, None)
            cmd = (event.message.text or "").strip()
            if not cmd:
                return

            await event.respond(f"Выполняю: {cmd}...")
            from host.executor import execute_shell, format_shell_result
            result = await execute_shell(cmd, timeout=60)
            output = format_shell_result(result)
            exit_code = result.get("returncode", "?")
            status_text = "[OK]" if result.get("ok") else "[ERROR]"

            # Разбиваем если длинный
            header = f"{status_text} Команда: {cmd}\nExit code: {exit_code}\n\n"
            full = header + (f"```\n{output}\n```" if output else "(нет вывода)")
            if len(full) > 4096:
                await event.respond(header)
                for i in range(0, len(output), 3900):
                    await event.respond(f"```\n{output[i:i+3900]}\n```")
            else:
                await event.respond(full)

            text, markup = main_menu()
            await event.respond(text, buttons=markup)
            return

            async def resolve_chat_id(target):
                resolved_id = None
                if target.isdigit():
                    resolved_id = int(target)
                elif target.lstrip('-').isdigit():
                    resolved_id = int(target)
                elif target.startswith("https://t.me/"):
                    username = target.split("https://t.me/", 1)[1].split("?")[0].strip()
                    entity = await main_client.get_entity(username)
                    resolved_id = entity.id
                elif target.startswith("@"):
                    entity = await main_client.get_entity(target)
                    resolved_id = entity.id
                return resolved_id

            async def handle_mem_action(target_input, state_dict, action_func, success_msg, err_msg):
                state_dict.pop(event.sender_id, None)
                try:
                    resolved_id = await resolve_chat_id(target_input)
                    if resolved_id:
                        success = action_func(resolved_id)
                        msg = f"{success_msg} ({resolved_id})" if success else err_msg
                        await event.respond(msg, buttons=[[Button.inline("В меню памяти", b"mem_menu")]])
                    else:
                        await event.respond("Чат не найден", buttons=[[Button.inline("Назад", b"mem_menu")]])
                except Exception as e:
                    await event.respond(f"Ошибка: {e}", buttons=[[Button.inline("Назад", b"mem_menu")]])

            # Просмотр истории сообщений
            if _waiting_mem_view_msgs.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                _waiting_mem_view_msgs.pop(event.sender_id, None)
                try:
                    resolved_id = await resolve_chat_id(target)
                    if resolved_id:
                        from memory.sqlite import get_short_memory
                        msgs = get_short_memory(resolved_id, limit=20)
                        if not msgs:
                            text = f"История сообщений для {resolved_id} пуста."
                        else:
                            text = f"Последние 20 сообщений для {resolved_id}:\n\n" + "\n".join(f"- {m}" for m in msgs)
                        await event.respond(text, buttons=[[Button.inline("В меню памяти", b"mem_menu")]])
                    else:
                        await event.respond("Чат не найден", buttons=[[Button.inline("Назад", b"mem_menu")]])
                except Exception as e:
                    await event.respond(f"Ошибка: {e}", buttons=[[Button.inline("Назад", b"mem_menu")]])

            # Просмотр саммари
            elif _waiting_mem_view_sums.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                _waiting_mem_view_sums.pop(event.sender_id, None)
                try:
                    resolved_id = await resolve_chat_id(target)
                    if resolved_id:
                        from memory.sqlite import get_summaries
                        sums = get_summaries(resolved_id, limit=5)
                        if not sums:
                            text = f"Саммари для {resolved_id} отсутствует."
                        else:
                            text = f"Саммари диалога {resolved_id}:\n\n" + "\n\n".join(f"• {s}" for s in sums)
                        await event.respond(text, buttons=[[Button.inline("В меню памяти", b"mem_menu")]])
                    else:
                        await event.respond("Чат не найден", buttons=[[Button.inline("Назад", b"mem_menu")]])
                except Exception as e:
                    await event.respond(f"Ошибка: {e}", buttons=[[Button.inline("Назад", b"mem_menu")]])

            # Принудительная генерация саммари
            elif _waiting_mem_gen_sum.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                _waiting_mem_gen_sum.pop(event.sender_id, None)
                try:
                    resolved_id = await resolve_chat_id(target)
                    if resolved_id:
                        from memory.sqlite import get_short_memory
                        from memory.summarizer import summarize_chat_history
                        short = get_short_memory(resolved_id, 100)
                        if not short:
                            await event.respond("Недостаточно сообщений для генерации саммари.", buttons=[[Button.inline("Назад", b"mem_menu")]])
                            return
                        await event.respond("Запускаю генерацию саммари...")
                        await summarize_chat_history(resolved_id, short, OWNER_ID)
                        await event.respond("Саммари успешно сгенерировано и обновлено в БД!", buttons=[[Button.inline("В меню памяти", b"mem_menu")]])
                    else:
                        await event.respond("Чат не найден", buttons=[[Button.inline("Назад", b"mem_menu")]])
                except Exception as e:
                    await event.respond(f"Ошибка генерации саммари: {e}", buttons=[[Button.inline("Назад", b"mem_menu")]])

            # Полное удаление памяти
            elif _waiting_mem_clear_all.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                from memory.sqlite import clear_chat_context
                await handle_mem_action(target, _waiting_mem_clear_all, clear_chat_context, "Вся память успешно удалена", "Ошибка удаления памяти")

            # Удаление только сообщений
            elif _waiting_mem_clear_msgs.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                from memory.sqlite import clear_chat_messages
                await handle_mem_action(target, _waiting_mem_clear_msgs, clear_chat_messages, "История сообщений успешно удалена", "Ошибка удаления истории")

            # Удаление только саммари
            elif _waiting_mem_clear_sums.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target: return
                from memory.sqlite import clear_chat_summaries
                await handle_mem_action(target, _waiting_mem_clear_sums, clear_chat_summaries, "Все саммари успешно удалены", "Ошибка удаления саммари")

            # Очистка старого контекста (для совместимости)
            elif _waiting_clear_context.get(event.sender_id):
                target = (event.message.text or "").strip()
                if not target:
                    return
                from memory.sqlite import clear_chat_context
                await handle_mem_action(target, _waiting_clear_context, clear_chat_context, "Контекст чата успешно очищен", "Ошибка очистки")

            # Ожидание отправки стикера для добавления в БД
            elif _waiting_sticker_file.get(event.sender_id):
                if not event.message.sticker:
                    await event.respond("Это не стикер. Пожалуйста, отправь стикер:", buttons=[[Button.inline("Отмена", b"sticker_menu")]])
                    return
                file_id = event.message.file.id
                _waiting_sticker_file.pop(event.sender_id, None)
                _waiting_sticker_desc[event.sender_id] = file_id
                await event.respond("Стикер получен! Теперь отправь ключевое слово для этого стикера (например, 'смех'):", buttons=[[Button.inline("Отмена", b"sticker_menu")]])
                return

            # Ожидание описания стикера
            elif _waiting_sticker_desc.get(event.sender_id):
                description = (event.message.text or "").strip().lower()
                if not description:
                    return
                file_id = _waiting_sticker_desc.pop(event.sender_id, None)
                from memory.sqlite import save_sticker
                save_sticker(file_id, description)
                await event.respond(f"Стикер для ключевого слова '{description}' успешно сохранен в базу!", buttons=[[Button.inline("В меню стикеров", b"sticker_menu")]])
                return

            # Ожидание удаления стикера
            elif _waiting_sticker_delete.get(event.sender_id):
                description = (event.message.text or "").strip().lower()
                if not description:
                    return
                _waiting_sticker_delete.pop(event.sender_id, None)
                from memory.sqlite import delete_sticker
                success = delete_sticker(description)
                msg = f"Стикер с описанием '{description}' успешно удален из базы." if success else "Ошибка удаления стикера."
                await event.respond(msg, buttons=[[Button.inline("В меню стикеров", b"sticker_menu")]])
                return


def _clear_state(user_id):
    _waiting_clear_context.pop(user_id, None)
    _waiting_mem_view_msgs.pop(user_id, None)
    _waiting_mem_view_sums.pop(user_id, None)
    _waiting_mem_gen_sum.pop(user_id, None)
    _waiting_mem_clear_all.pop(user_id, None)
    _waiting_mem_clear_msgs.pop(user_id, None)
    _waiting_mem_clear_sums.pop(user_id, None)
    _waiting_sticker_file.pop(user_id, None)
    _waiting_sticker_desc.pop(user_id, None)
    _waiting_sticker_delete.pop(user_id, None)
    _waiting_shell_cmd.pop(user_id, None)
    _waiting_name.pop(user_id, None)
    _waiting_bio.pop(user_id, None)
    _waiting_username.pop(user_id, None)
    _waiting_avatar.pop(user_id, None)
    _waiting_timezone.pop(user_id, None)
    _waiting_add_schedule.pop(user_id, None)
    _waiting_delete_schedule.pop(user_id, None)
    _waiting_bot_name.pop(user_id, None)
    _waiting_add_trigger.pop(user_id, None)
    _waiting_delete_trigger.pop(user_id, None)


async def _get_system_status(main_client) -> str:
    from tg.events import get_uptime, get_ram_usage
    from tg.state import get_action
    from host.executor import get_system_info

    db_size_kb = 0
    if os.path.exists(DB_PATH):
        db_size_kb = os.path.getsize(DB_PATH) // 1024

    userbot_status = "Онлайн" if main_client and main_client.is_connected() else "Оффлайн"
    info = await get_system_info()

    return (
        f"Статус Clawd:\n\n"
        f"Занятие: {get_action()}\n"
        f"Юзербот: {userbot_status}\n"
        f"Uptime: {get_uptime()}\n"
        f"RAM: {get_ram_usage()}\n"
        f"OS: {info.get('os', '?')}\n"
        f"Load: {' / '.join(info.get('load_avg', ['?', '?', '?']))}\n"
        f"Disk: {info.get('disk', '?')}\n"
        f"IP: {info.get('ip', '?')}\n"
        f"Размер БД: {db_size_kb} KB"
    )


async def _show_settings_menu(bot, chat_id, event=None):
    text = (
        "Настройки бота\n\n"
        "Выберите раздел для изменения настроек профиля аккаунта, расписания задач или системных параметров."
    )
    markup = [
        [Button.inline("Профиль аккаунта", b"profile_settings")],
        [Button.inline("Системный конфиг", b"bot_config_menu")],
        [Button.inline("Планировщик задач", b"schedulers_menu")],
        [Button.inline("В главное меню", b"main_menu")]
    ]
    if event and hasattr(event, 'edit'):
        await event.edit(text, buttons=markup)
    else:
        await bot.send_message(chat_id, text, buttons=markup)


async def _show_profile_settings(bot, chat_id, event=None):
    try:
        from tg.client import get_client
        main_client = get_client()
        me = await main_client.get_me()
        from telethon.tl.functions.users import GetFullUserRequest
        full = await main_client(GetFullUserRequest(me.id))
        bio = full.full_user.about or "(нет)"
        name_str = f"{me.first_name or ''} {me.last_name or ''}".strip() or "(нет)"
        username_str = f"@{me.username}" if me.username else "(нет)"

        text = (
            f"Настройки профиля\n\n"
            f"Имя в Telegram: {name_str}\n"
            f"Юзернейм: {username_str}\n"
            f"О себе: {bio}\n\n"
            f"Выберите параметр для изменения:"
        )
        markup = [
            [Button.inline("Изменить имя в Telegram", b"set_name"),
             Button.inline("Изменить био", b"set_bio")],
            [Button.inline("Изменить аватар", b"set_avatar"),
             Button.inline("Изменить юзернейм", b"set_username")],
            [Button.inline("Назад", b"settings_menu")]
        ]
        if event and hasattr(event, 'edit'):
            await event.edit(text, buttons=markup)
        else:
            await bot.send_message(chat_id, text, buttons=markup)
    except Exception as e:
        logger.error(f"[Panel] Error showing profile settings: {e}")
        error_text = f"Не удалось загрузить настройки профиля: {e}"
        if event and hasattr(event, 'edit'):
            await event.edit(error_text, buttons=[[Button.inline("Назад", b"settings_menu")]])
        else:
            await bot.send_message(chat_id, error_text, buttons=[[Button.inline("Назад", b"settings_menu")]])


async def _show_bot_config_menu(bot, chat_id, event=None):
    try:
        from config import TIMEZONE
        tz = get_setting("timezone", TIMEZONE)
        primary_model = get_setting("primary_model", "codexsale/gpt-5.5")
        bot_name = get_setting("bot_name", "Claw'd")
        bot_trigger = get_setting("bot_trigger", "Claw'd")
        bot_lang = get_setting("bot_language", "ru")

        text = (
            f"Системный конфиг\n\n"
            f"Системное имя бота: {bot_name}\n"
            f"Триггеры в группах: {bot_trigger}\n"
            f"Язык общения: {bot_lang}\n"
            f"Активная модель: {primary_model}\n"
            f"Часовой пояс: {tz}\n\n"
            f"Выберите параметр для изменения:"
        )
        markup = [
            [Button.inline("Сменить модель", b"select_model_menu"),
             Button.inline("Сменить имя бота", b"set_bot_name_start")],
            [Button.inline("Настройка триггеров", b"triggers_menu"),
             Button.inline("Сменить язык", b"set_bot_lang_menu")],
            [Button.inline("Сменить часовой пояс", b"set_timezone_start")],
            [Button.inline("Назад", b"settings_menu")]
        ]
        if event and hasattr(event, 'edit'):
            await event.edit(text, buttons=markup)
        else:
            await bot.send_message(chat_id, text, buttons=markup)
    except Exception as e:
        logger.error(f"[Panel] Error config menu: {e}")


async def _show_select_model_menu(bot, chat_id, event=None):
    text = (
        "Выбор приоритетной модели LLM\n\n"
        "Выберите модель, которая будет использоваться по умолчанию для обработки сообщений:"
    )
    markup = [
        [Button.inline("GPT-5.5 (Codex)", b"set_model_gpt55")],
        [Button.inline("GPT-5.4 (Codex)", b"set_model_gpt54")],
        [Button.inline("GPT-4o (Codex)", b"set_model_gpt4o")],
        [Button.inline("Claude 3.5 Sonnet (Codex)", b"set_model_claude35")],
        [Button.inline("Gemini 2.0 Flash (Free)", b"set_model_gemini2")],
        [Button.inline("Назад", b"bot_config_menu")]
    ]
    if event and hasattr(event, 'edit'):
        await event.edit(text, buttons=markup)
    else:
        await bot.send_message(chat_id, text, buttons=markup)


async def _show_select_lang_menu(bot, chat_id, event=None):
    text = (
        "Выбор языка общения бота\n\n"
        "Выберите язык, который бот будет использовать по умолчанию:"
    )
    markup = [
        [Button.inline("Русский (ru)", b"set_lang_ru")],
        [Button.inline("English (en)", b"set_lang_en")],
        [Button.inline("Назад", b"bot_config_menu")]
    ]
    if event and hasattr(event, 'edit'):
        await event.edit(text, buttons=markup)
    else:
        await bot.send_message(chat_id, text, buttons=markup)


async def _show_triggers_menu(bot, chat_id, event=None):
    try:
        bot_trigger = get_setting("bot_trigger", "Claw'd")
        triggers = [t.strip() for t in bot_trigger.split(",") if t.strip()]
        
        lines = []
        if not triggers:
            lines.append("Список триггеров пуст.")
        else:
            lines.append("Текущие триггеры:")
            for idx, t in enumerate(triggers, 1):
                lines.append(f"{idx}. {t}")
        
        text = (
            "Управление триггерами в группах\n\n"
            + "\n".join(lines) +
            "\n\nВыберите действие:"
        )
        markup = [
            [Button.inline("Добавить триггер", b"add_trigger_start"),
             Button.inline("Удалить триггер", b"delete_trigger_start")],
            [Button.inline("Назад", b"bot_config_menu")]
        ]
        if event and hasattr(event, 'edit'):
            await event.edit(text, buttons=markup)
        else:
            await bot.send_message(chat_id, text, buttons=markup)
    except Exception as e:
        logger.error(f"[Panel] Error triggers menu: {e}")


async def _show_schedulers_menu(bot, chat_id, event=None):
    try:
        from memory.sqlite import get_active_schedules
        schedules = get_active_schedules()
        
        lines = []
        if not schedules:
            lines.append("Активные запланированные задачи отсутствуют.")
        else:
            for s in schedules:
                sid, ttype, target, payload, stype, sval, lrun, nrun = s
                lines.append(
                    f"ID: {sid} | Тип: {ttype}\n"
                    f"Режим: {stype} ({sval})\n"
                    f"Следующий запуск: {nrun or 'неизвестно'}\n"
                    f"Поручение: {payload if len(payload) <= 2000 else f'{payload[:2000]}...'}"
                )
        
        text = (
            "Планировщик задач\n\n"
            + "\n\n".join(lines) +
            "\n\nУправляйте задачами с помощью кнопок ниже:"
        )
        markup = [
            [Button.inline("Добавить задачу", b"add_sched_start"),
             Button.inline("Удалить задачу", b"delete_sched_start")],
            [Button.inline("Назад", b"settings_menu")]
        ]
        if event and hasattr(event, 'edit'):
            await event.edit(text, buttons=markup)
        else:
            await bot.send_message(chat_id, text, buttons=markup)
    except Exception as e:
        logger.error(f"[Panel] Error schedules menu: {e}")
