"""Config yükleme ve yapısal log — tüm modüllerin paylaştığı ince katman."""
from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """config/<name>.yaml dosyasını okur (uzantı verilmese de ekler)."""
    fname = name if name.endswith((".yaml", ".yml")) else f"{name}.yaml"
    path = CONFIG_DIR / fname
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def style() -> dict[str, Any]:
    return load_yaml("style")


def pillars() -> dict[str, Any]:
    return load_yaml("pillars")


def settings() -> dict[str, Any]:
    return load_yaml("settings")


def env(key: str, default: str = "") -> str:
    """Ortam değişkeni; .env varsa python-dotenv ile yüklenir (bir kez)."""
    _load_dotenv_once()
    return os.environ.get(key, default)


_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    try:
        from dotenv import load_dotenv  # opsiyonel bağımlılık
        load_dotenv(ROOT / ".env")
    except Exception:
        pass  # .env yoksa veya paket yoksa sorun değil (Actions'ta secrets kullanılır)


# ---- Yapısal log -----------------------------------------------------------
_LOG_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Adım adım izlenebilir, tek satır formatlı logger döndürür."""
    global _LOG_CONFIGURED
    if not _LOG_CONFIGURED:
        logging.basicConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"),
            format="%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stdout,
        )
        _LOG_CONFIGURED = True
    return logging.getLogger(name)
