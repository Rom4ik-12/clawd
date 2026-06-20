"""
host/executor.py — Полный доступ к хосту: shell, файлы, системная инфа
"""
import asyncio
import os
import logging
import platform
import shutil
from datetime import datetime

logger = logging.getLogger("host")


async def execute_shell(command: str, timeout: int = 30) -> dict:
    """
    Выполняет bash-команду на хосте.
    Возвращает {'stdout': str, 'stderr': str, 'returncode': int, 'ok': bool}
    """
    logger.info(f"🖥️ [Shell] Выполняю: {command}")
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "stdout": "",
                "stderr": f"Команда прервана по таймауту ({timeout}с)",
                "returncode": -1,
                "ok": False
            }

        return {
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0
        }
    except Exception as e:
        logger.error(f"[Shell] Ошибка: {e}")
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "ok": False
        }


def format_shell_result(result: dict) -> str:
    """Форматирует результат shell-команды для отправки в чат."""
    parts = []
    if result["stdout"]:
        parts.append(result["stdout"])
    if result["stderr"]:
        parts.append(f"[stderr] {result['stderr']}")
    if not parts:
        code = result.get("returncode", "?")
        parts.append(f"Команда выполнена (exit code: {code})")
    return "\n".join(parts)


async def read_file(path: str, max_bytes: int = 50_000) -> str:
    """Читает файл с хоста, возвращает содержимое как строку."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            return f"Файл не найден: {path}"
        size = os.path.getsize(expanded)
        with open(expanded, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
        suffix = f"\n\n[... файл обрезан, показано {len(content)}/{size} байт ...]" if size > max_bytes else ""
        return content + suffix
    except Exception as e:
        return f"Ошибка чтения файла: {e}"


async def write_file(path: str, content: str, append: bool = False) -> str:
    """Записывает файл на хосте."""
    try:
        expanded = os.path.expanduser(path)
        # Создаём директории если нужно
        os.makedirs(os.path.dirname(expanded) if os.path.dirname(expanded) else ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(expanded, mode, encoding="utf-8") as f:
            f.write(content)
        action = "дописано" if append else "записано"
        return f"✅ Файл {path} {action} ({len(content)} символов)"
    except Exception as e:
        return f"Ошибка записи файла: {e}"


async def edit_file(path: str, search_text: str, replace_text: str) -> str:
    """Находит search_text в файле и заменяет на replace_text."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            return f"Файл не найден: {path}"
        with open(expanded, "r", encoding="utf-8") as f:
            content = f.read()
        if search_text not in content:
            return f"❌ Фрагмент для замены не найден в файле {path}. Убедитесь, что поиск совпадает точно."
        new_content = content.replace(search_text, replace_text)
        with open(expanded, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"✅ Успешно произведена замена в файле {path}."
    except Exception as e:
        return f"Ошибка при редактировании файла: {e}"


async def list_directory(path: str = ".") -> str:
    """Возвращает список файлов/папок в директории."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            return f"Директория не найдена: {path}"
        items = sorted(os.listdir(expanded))
        result = []
        for item in items:
            full = os.path.join(expanded, item)
            if os.path.isdir(full):
                result.append(f"📁 {item}/")
            else:
                size = os.path.getsize(full)
                result.append(f"📄 {item} ({_fmt_size(size)})")
        return "\n".join(result) if result else "Директория пуста"
    except Exception as e:
        return f"Ошибка листинга: {e}"


async def get_system_info() -> dict:
    """Системная информация: CPU, RAM, диск, uptime, Python."""
    info = {}
    try:
        # CPU
        res = await execute_shell("grep -c processor /proc/cpuinfo")
        info["cpu_cores"] = res["stdout"] or "?"
        res = await execute_shell("cat /proc/loadavg")
        info["load_avg"] = res["stdout"].split()[:3] if res["stdout"] else ["?", "?", "?"]

        # RAM
        res = await execute_shell("free -m | awk 'NR==2{printf \"%s/%s MB\", $3, $2}'")
        info["ram"] = res["stdout"] or "?"

        # Disk
        res = await execute_shell("df -h / | awk 'NR==2{print $3\"/\"$2\" used (\"$5\")\"}'")
        info["disk"] = res["stdout"] or "?"

        # Uptime
        res = await execute_shell("uptime -p 2>/dev/null || uptime")
        info["uptime"] = res["stdout"] or "?"

        # Python
        info["python"] = platform.python_version()

        # OS
        info["os"] = platform.system() + " " + platform.release()

        # IP
        res = await execute_shell("curl -s --max-time 3 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}'")
        info["ip"] = res["stdout"] or "?"

    except Exception as e:
        info["error"] = str(e)

    return info


def format_system_info(info: dict) -> str:
    """Форматирует системную инфу для вывода."""
    lines = [
        f"🖥️ **Системная информация:**",
        f"  OS: {info.get('os', '?')}",
        f"  Python: {info.get('python', '?')}",
        f"  CPU cores: {info.get('cpu_cores', '?')}",
        f"  Load avg: {' / '.join(info.get('load_avg', ['?', '?', '?']))}",
        f"  RAM: {info.get('ram', '?')}",
        f"  Disk: {info.get('disk', '?')}",
        f"  Uptime: {info.get('uptime', '?')}",
        f"  IP: {info.get('ip', '?')}",
    ]
    return "\n".join(lines)


async def download_file(url: str, dest: str = None) -> str:
    """Скачивает файл по URL на хост."""
    try:
        if not dest:
            filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
            dest = os.path.join("database/cache", filename)

        os.makedirs(os.path.dirname(dest) if os.path.dirname(dest) else ".", exist_ok=True)
        result = await execute_shell(f"curl -L --max-time 60 -o '{dest}' '{url}'")

        if result["ok"] and os.path.exists(dest):
            size = _fmt_size(os.path.getsize(dest))
            return f"✅ Файл скачан: {dest} ({size})"
        else:
            return f"❌ Ошибка скачивания: {result['stderr']}"
    except Exception as e:
        return f"❌ Ошибка: {e}"


def _fmt_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


async def get_video_frames(path: str, count: int = 5) -> str:
    """Извлекает count кадров из видеофайла и сохраняет в database/cache."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            return f"Видеофайл не найден: {path}"
            
        # Получаем длительность
        cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 '{expanded}'"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        try:
            duration = float(stdout.decode().strip())
        except Exception:
            duration = 10.0 # резервное значение
            
        interval = duration / (count + 1)
        frames = []
        os.makedirs("database/cache", exist_ok=True)
        for i in range(1, count + 1):
            ss = i * interval
            out_path = f"database/cache/frame_{int(ss)}.jpg"
            cmd_extract = f"ffmpeg -y -ss {ss} -i '{expanded}' -vframes 1 -q:v 2 '{out_path}'"
            proc_extract = await asyncio.create_subprocess_shell(cmd_extract, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc_extract.communicate()
            if os.path.exists(out_path):
                frames.append(out_path)
                
        if not frames:
            return "❌ Не удалось извлечь кадры из видео."
        return f"✅ Извлечено {len(frames)} кадров из видео:\n" + "\n".join(frames)
    except Exception as e:
        return f"Ошибка при извлечении кадров: {e}"
