"""Paths and config loading."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONTENT_DIR = ROOT / "content"
DATA_DIR = ROOT / "data"
IMPORTS_DIR = DATA_DIR / "imports"
MANUAL_DIR = DATA_DIR / "manual"
HISTORY_FILE = DATA_DIR / "history" / "prices.csv"
SEED_FILE = DATA_DIR / "seed" / "snapshot.json"
JOURNAL_FILE = DATA_DIR / "journal.csv"
SITE_DIR = ROOT / "site"
SITE_DATA = SITE_DIR / "data"
DOWNLOADS = SITE_DIR / "downloads"

GROUPS = [("equities", "EQUITIES"), ("fixed_income", "FIXED INCOME"), ("others", "OTHERS")]


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def instruments() -> list[dict]:
    items = load_yaml(CONFIG_DIR / "instruments.yaml")["instruments"]
    keys = [i["key"] for i in items]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate instrument keys in config/instruments.yaml")
    return items


def settings() -> dict:
    return load_yaml(CONFIG_DIR / "settings.yaml")
