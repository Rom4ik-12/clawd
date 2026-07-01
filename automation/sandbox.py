import subprocess
import os
import tempfile
import asyncio

async def run_in_sandbox(language: str, code: str, timeout_seconds: int = 30) -> str:
    """
    Запускает код (python/bash) в изолированном Docker-контейнере.
    Возвращает stdout/stderr.
    """
    # Создаем временную директорию для маунта (если нужно)
    with tempfile.TemporaryDirectory() as temp_dir:
        
        if language.lower() in ['python', 'py']:
            script_path = os.path.join(temp_dir, 'script.py')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
                
            cmd = [
                'docker', 'run', '--rm',
                '--network', 'none', # Отключаем сеть для безопасности
                '--memory', '256m',
                '--cpus', '0.5',
                '-v', f'{temp_dir}:/app',
                '-w', '/app',
                'python:3.12-slim',
                'python', 'script.py'
            ]
        elif language.lower() in ['bash', 'sh']:
            script_path = os.path.join(temp_dir, 'script.sh')
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
                
            cmd = [
                'docker', 'run', '--rm',
                '--network', 'none',
                '--memory', '256m',
                '--cpus', '0.5',
                '-v', f'{temp_dir}:/app',
                '-w', '/app',
                'ubuntu:latest',
                'bash', 'script.sh'
            ]
        else:
            return f"Error: Неподдерживаемый язык {language}. Доступны: python, bash."

        try:
            # Запускаем синхронный subprocess асинхронно
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                return f"Error: Превышено время ожидания ({timeout_seconds} сек)"
                
            output = ""
            if stdout:
                output += stdout.decode('utf-8')
            if stderr:
                if output: output += "\n"
                output += f"STDERR:\n{stderr.decode('utf-8')}"
                
            if not output:
                output = "(Код выполнен успешно, нет вывода)"
                
            return output
            
        except Exception as e:
            return f"Sandbox execution error: {str(e)}"
