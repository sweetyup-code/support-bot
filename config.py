"""
Настройки пользователя. Читаются из %APPDATA%\\SupportBot\\config.json.
При первом запуске — создаётся с дефолтными значениями.
"""
import json
import os

from paths import CONFIG_FILE

DEFAULTS = {
    "operator_id": "6702",
    "base_url": "https://appslab.helpdeskeddy.com",
    "list_url_open": "https://appslab.helpdeskeddy.com/ru/ticket/list/filter/id/3/page/1",
    "check_interval_sec": 15,
    "dry_run": True,
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULTS)
        return dict(DEFAULTS)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    # дозаполним отсутствующие ключи дефолтами
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    return data


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get(key: str):
    return load_config()[key]