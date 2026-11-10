"""运行时状态：变量表、好感度、当前节点 line_index、历史回看、JSON 多槽位存档。

变量值只允许 JSON 可序列化类型；未定义变量读取为 0（`@if affection >= 3`
零声明可用）；好感度就是常规变量 ``affection``（State.affection 为其视图）。
"""

from __future__ import annotations

import json
import operator
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .script import Comparison, Condition, VarRef

__all__ = ["StateError", "SaveError", "HistoryEntry", "State",
           "evaluate_condition", "SAVE_VERSION"]

SAVE_VERSION = 1
HISTORY_LIMIT = 500
_OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge,
        "<=": operator.le, ">": operator.gt, "<": operator.lt}


class StateError(RuntimeError):
    """状态非法操作。"""


class SaveError(StateError):
    """存档/读档失败。"""


@dataclass
class HistoryEntry:
    """一条历史记录（台词/旁白/选项/场景/演出/结局）。"""
    kind: str                       # line / narration / choice / scene / fx / ending
    speaker: Optional[str] = None
    text: Optional[str] = None
    scene: Optional[str] = None
    choice: Optional[dict] = None   # {"index": n, "text": ...}
    lineno: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(kind=d.get("kind", "line"), speaker=d.get("speaker"),
                   text=d.get("text"), scene=d.get("scene"),
                   choice=d.get("choice"), lineno=int(d.get("lineno", 0)))


def _compare(left: Any, op: str, right: Any) -> bool:
    """按运算符比较；混合类型（str vs int）比较抛 TypeError 时视为不成立。"""
    fn = _OPS.get(op)
    if fn is None:
        raise StateError(f"未知比较运算符 {op!r}")
    try:
        return bool(fn(left, right))
    except TypeError:
        return False


def evaluate_condition(cond: Condition, variables: dict) -> bool:
    """对条件表达式求值：and 优先于 or；未定义变量按 0。"""
    # 1) 把 Comparison 都换算成 bool
    values: list = []
    for tok in cond.tokens:
        if isinstance(tok, Comparison):
            left = variables.get(tok.var, 0)
            right = variables.get(tok.value.name, 0) if isinstance(tok.value, VarRef) else tok.value
            values.append(_compare(left, tok.op, right))
        else:
            values.append(tok)
    # 2) 先归并所有 and，再归并所有 or（and 优先级高于 or）
    collapsed: list = []
    i = 0
    while i < len(values):
        item = values[i]
        if item == "and":
            i += 1
            continue
        if i + 1 < len(values) and values[i + 1] == "and":
            nxt = values[i + 2] if i + 2 < len(values) else False
            collapsed.append(bool(item) and bool(nxt))
            i += 3
        else:
            collapsed.append(item)
            i += 1
    result = False
    for item in collapsed:
        if item == "or":
            continue
        result = result or bool(item)
    return result


# --------------------------------------------------------------------------- 状态


@dataclass
class State:
    """一局游戏的完整可序列化状态。"""
    script_name: str = "untitled"
    line_index: int = 0            # 当前执行到的行号（节点）
    scene: Optional[str] = None    # 当前场景标题
    variables: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    ending: Optional[str] = None   # 已达成的结局（未结束为 None）

    # ---- 变量 ------------------------------------------------------------

    @property
    def affection(self) -> int:
        """好感度便捷视图（默认 0）。"""
        return self.variables.get("affection", 0)

    @affection.setter
    def affection(self, value: int) -> None:
        self.variables["affection"] = value

    def get(self, name: str, default: Any = 0) -> Any:
        return self.variables.get(name, default)

    def set(self, name: str, value: Any) -> None:
        if not isinstance(value, (int, float, str, bool)) and value is not None:
            raise StateError(f"变量 {name!r} 的值 {value!r} 不是 JSON 可序列化类型")
        self.variables[name] = value

    def apply(self, name: str, op: str, value: Any) -> None:
        """执行 `name op value`，op ∈ {=, +=, -=}。"""
        if op == "=":
            self.set(name, value)
            return
        current = self.variables.get(name, 0)
        if not isinstance(current, (int, float)) or not isinstance(value, (int, float)):
            raise StateError(f"无法对非数字执行 {op}: {name}={current!r} {op} {value!r}")
        self.variables[name] = current + value if op == "+=" else current - value

    def satisfies(self, cond: Optional[Condition]) -> bool:
        """条件求值；None 视为恒真（无条件）。"""
        if cond is None:
            return True
        return evaluate_condition(cond, self.variables)

    # ---- 历史 ------------------------------------------------------------

    def record(self, entry: HistoryEntry) -> None:
        self.history.append(entry)
        if len(self.history) > HISTORY_LIMIT:
            del self.history[:len(self.history) - HISTORY_LIMIT]

    # ---- 序列化 ----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "script": self.script_name,
            "line_index": self.line_index,
            "scene": self.scene,
            "ending": self.ending,
            "variables": self.variables,
            "history": [h.to_dict() for h in self.history],
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def from_dict(cls, d: dict, expect_script: Optional[str] = None) -> "State":
        if d.get("version") != SAVE_VERSION:
            raise SaveError(f"存档版本不兼容: {d.get('version')!r}")
        script = d.get("script")
        if expect_script is not None and script != expect_script:
            raise SaveError(f"存档属于剧本 {script!r}，当前剧本为 {expect_script!r}")
        return cls(
            script_name=script or "untitled",
            line_index=int(d.get("line_index", 0)),
            scene=d.get("scene"),
            ending=d.get("ending"),
            variables=dict(d.get("variables") or {}),
            history=[HistoryEntry.from_dict(h) for h in d.get("history") or []],
        )

    @staticmethod
    def slot_path(slot: int, save_dir) -> Path:
        if not isinstance(slot, int) or slot < 1:
            raise SaveError(f"存档位编号必须是 >=1 的整数，得到 {slot!r}")
        return Path(save_dir) / f"slot_{slot}.json"

    def save_to(self, slot: int, save_dir) -> Path:
        path = self.slot_path(slot, save_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    @classmethod
    def load_from(cls, slot: int, save_dir, expect_script: Optional[str] = None) -> "State":
        path = cls.slot_path(slot, save_dir)
        if not path.is_file():
            raise SaveError(f"存档位 {slot} 为空（{path} 不存在）")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SaveError(f"存档损坏: {path} ({exc})") from exc
        return cls.from_dict(data, expect_script=expect_script)

    @staticmethod
    def list_slots(save_dir) -> list:
        """列出已有存档位编号与保存时间。"""
        d = Path(save_dir)
        if not d.is_dir():
            return []
        out = []
        for p in sorted(d.glob("slot_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append({"slot": int(p.stem.split("_")[1]),
                            "script": data.get("script"),
                            "saved_at": data.get("saved_at"),
                            "scene": data.get("scene")})
            except (json.JSONDecodeError, OSError, ValueError):
                out.append({"slot": p.stem, "script": None,
                            "saved_at": None, "scene": "（损坏）"})
        return out
