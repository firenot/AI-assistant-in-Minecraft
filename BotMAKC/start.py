import subprocess
import time
import os

# ---- Определяем корень проекта ----
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Путь к Python из виртуального окружения ----
# Для Windows:
python_exe = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")


# ---- Запуск Flask-сервера ----
flask_app_path = os.path.join(PROJECT_ROOT, "UI-AI", "app.py")
flask_proc = subprocess.Popen([python_exe, flask_app_path])
time.sleep(2)  # ждём запуска сервера

# ---- Запуск чата ----
run_ai_path = os.path.join(PROJECT_ROOT, "UI-AI", "run_ai.py")
subprocess.call([python_exe, run_ai_path])

# ---- Остановка Flask ----
flask_proc.terminate()