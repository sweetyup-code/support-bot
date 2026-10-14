r"""
Централизованные пути для проекта.
- APP_DIR:  папка рядом с .exe (или с .py при разработке) — читаем .json/.pkl
- DATA_DIR: %APPDATA%\SupportBot — пишем логи, профиль Chrome, config
"""
import os
import sys


def _app_dir() -> str:
    """Папка приложения: рядом с .exe или с исходниками."""
    if getattr(sys, "frozen", False):
        # запущено как .exe, собранный PyInstaller
        return os.path.dirname(sys.executable)
    # запущено как .py
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Папка для данных пользователя (%APPDATA%\\SupportBot)."""
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "SupportBot")
    os.makedirs(base, exist_ok=True)
    return base


APP_DIR = _app_dir()
DATA_DIR = _data_dir()

# файлы данных
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
CHROME_PROFILE = os.path.join(DATA_DIR, "chrome-profile")
LOG_DIR = os.path.join(DATA_DIR, "logs")
MODEL_CACHE_DIR = os.path.join(DATA_DIR, "models")

for d in (CHROME_PROFILE, LOG_DIR, MODEL_CACHE_DIR):
    os.makedirs(d, exist_ok=True)

# Chrome — либо встроенный portable (bin/chrome/chrome.exe),
# либо системный (C:\Program Files\Google\Chrome\...)
CHROME_PORTABLE = os.path.join(APP_DIR, "bin", "chrome", "chrome.exe")
CHROME_SYSTEM = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_EXE = CHROME_PORTABLE if os.path.exists(CHROME_PORTABLE) else CHROME_SYSTEM


def find_json(name: str) -> str:
    """Ищет файл сначала рядом с .exe, потом в DATA_DIR."""
    p1 = os.path.join(APP_DIR, name)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(DATA_DIR, name)
    if os.path.exists(p2):
        return p2
    return p1  # вернём первый — путь для ошибки