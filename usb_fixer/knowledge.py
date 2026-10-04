"""Board/CPU/chipset knowledge, kept in data/knowledge.json so it can grow without code changes."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .snapshot import SystemInfo

DATA_FILE = Path(__file__).parent / "data" / "knowledge.json"


def load_rules(path: Path = DATA_FILE) -> list:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rules", [])


def bios_age_days(system: SystemInfo, today: date) -> Optional[int]:
    if system.bios_date is None:
        return None
    return (today - system.bios_date).days


def matches(when: dict, system: SystemInfo, today: date) -> bool:
    """True when every condition in ``when`` holds."""
    board = f"{system.board_manufacturer} {system.board_product}"
    if "board_regex" in when and not re.search(when["board_regex"], board, re.IGNORECASE):
        return False
    if "cpu_regex" in when and not re.search(when["cpu_regex"], system.cpu, re.IGNORECASE):
        return False
    if "controller_vendors" in when and not any(
        c.vendor_id in when["controller_vendors"] for c in system.controllers
    ):
        return False
    if "laptop" in when and system.is_laptop != when["laptop"]:
        return False
    if "bios_older_than_days" in when:
        age = bios_age_days(system, today)
        if age is None or age <= when["bios_older_than_days"]:
            return False
    return True
