"""pet.persist — JSON 存档：跨会话存活，损坏时优雅回退。

约定：load() 永不抛异常——损坏时先把原文件备份为 <name>.corrupt 再返回
None（由调用方开新档）；读入字段全部过一遍夹取，坏值不带进游戏。
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine import PetState, new_pet

SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = PROJECT_ROOT / "data" / "pet.json"

_FIELDS = ("name", "hunger", "mood", "energy", "health",
           "age_seconds", "stage_idx", "status", "action_left",
           "sleep_left", "stress_seconds", "grow_warned", "sick_noted",
           "last_tick", "born_at")
_STATUS = ("idle", "eating", "playing", "sleeping", "sick")
_0_100 = ("hunger", "mood", "energy", "health")


def save(pet: PetState, path: str | Path | None = None) -> Path:
    """把宠物写入 JSON 存档，返回实际路径。"""
    target = Path(path) if path else DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": SCHEMA_VERSION,
               **{f: getattr(pet, f) for f in _FIELDS}}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return target


def load(path: str | Path | None = None) -> PetState | None:
    """读档；无档或损坏返回 None（损坏文件备份为 .corrupt）。"""
    target = Path(path) if path else DEFAULT_PATH
    if not target.exists():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("存档不是 JSON 对象")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        _backup_corrupt(target)
        return None
    return _hydrate(raw)


def _backup_corrupt(target: Path) -> None:
    """把坏文件挪到旁边存证；任何失败都不影响主流程。"""
    try:
        bad = target.with_suffix(target.suffix + ".corrupt")
        bad.write_bytes(target.read_bytes())
    except OSError:
        pass


def _hydrate(raw: dict) -> PetState:
    """把 dict 填回 PetState：缺字段用默认，坏值夹取，绝不抛异常。"""
    pet = new_pet()
    for key in _FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        default = getattr(pet, key)
        if isinstance(default, bool):
            if isinstance(value, bool):
                setattr(pet, key, value)
        elif isinstance(default, float):
            if isinstance(value, (int, float)) and value == value:  # 非 NaN
                setattr(pet, key, float(value))
        elif isinstance(default, int):
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(pet, key, value)
        elif isinstance(default, str):
            if isinstance(value, str):
                setattr(pet, key, value)
    for key in _0_100:                       # 属性夹回 0-100
        setattr(pet, key, max(0.0, min(100.0, getattr(pet, key))))
    if pet.status not in _STATUS:
        pet.status = "idle"
    pet.stage_idx = max(0, min(pet.stage_idx, 3))
    pet.action_left = max(0.0, pet.action_left)
    pet.sleep_left = max(0.0, pet.sleep_left)
    pet.stress_seconds = max(0.0, pet.stress_seconds)
    pet.age_seconds = max(0.0, pet.age_seconds)
    return pet
