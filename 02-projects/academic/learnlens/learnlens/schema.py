"""LearnLens 数据模式：三类记录的数据类、校验与 JSON 序列化。

对应 RESEARCH-PLAN.md 第 2 节「数据资产与数据字典」的三路自产数据：

- :class:`StudySession` ← ``04-tools/study-timer/data/log.json`` 的一条时长记录
- :class:`DailyReport`  ← 每日学习日报 Markdown（母版见 ``05-ai/prompts/每日学习日报母版.md``）
- :class:`SelfTest`     ← 手动录入的自测成绩（``learnlens log-test``）

设计取舍（为什么这样写）：

- 校验放在 ``__post_init__``，构造即合法 —— 下游分析代码不必处处判脏数据；
- 序列化只用标准库 json，字段名与源数据保持一致，方便与 study-timer 互读；
- 三件事状态在计划书的 ``pending|done|partial`` 之外补了 ``missed``：
  母版规定回看时「保持 ``[ ]`` 即 missed」，缺这个状态就无法计算执行率（RQ2 的因变量）。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, TypeVar

__all__ = [
    "SchemaError",
    "TaskStatus",
    "TASK_STATUSES",
    "parse_accuracy",
    "StudySession",
    "TaskItem",
    "SelfTest",
    "DailyReport",
    "read_json",
    "write_json",
]

TaskStatus = Literal["pending", "done", "partial", "missed"]
#: 三件事的四种状态。pending = 新三件事还没到回看时点，不计入执行率分母。
TASK_STATUSES: tuple[str, ...] = ("pending", "done", "partial", "missed")


class SchemaError(ValueError):
    """数据校验失败。继承 ValueError，上层可按普通输入错误统一捕获。"""


# ---------- 通用小工具 ----------

def _parse_datetime(raw: Any, name: str) -> datetime:
    """把 ISO 时间串解析成 datetime，错误信息带上字段名便于定位。"""
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        raise SchemaError(f"字段 {name} 必须是 ISO 时间串，得到 {type(raw).__name__}")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SchemaError(f"字段 {name} 不是合法 ISO 时间：{raw!r}") from exc


def _parse_number(raw: Any, name: str) -> float:
    """JSON 数字 → float；显式拒绝 bool（它是 int 的子类，混进来只会埋雷）。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SchemaError(f"字段 {name} 必须是数字，得到 {raw!r}")
    value = float(raw)
    if not math.isfinite(value):
        raise SchemaError(f"字段 {name} 不能是 NaN/Infinity")
    return value


def _require_text(raw: Any, name: str) -> str:
    """非空文本字段：None / 非 str / 空白串都算错。"""
    if not isinstance(raw, str) or not raw.strip():
        raise SchemaError(f"字段 {name} 必须是非空字符串，得到 {raw!r}")
    return raw.strip()


def parse_accuracy(raw: str | float | int) -> float:
    """把人顺手写的正确率规范成 0–100 的浮点数。

    录入要在 30 秒内完成，所以同时接受三种最自然的写法：

    - ``"80%"`` / ``"80"`` → ``80.0``
    - ``"0.8"`` / ``0.85`` → ``80.0`` / ``85.0``（≤1 的数按比例记）
    - ``1`` / ``"1"``      → ``100.0``（比例记法的上限）

    为什么 ≤1 按比例：考研自测正确率几乎不会低于 1%，把 ``0.85`` 读成 0.85%
    才是真正的数据事故。
    """
    if isinstance(raw, bool):
        raise SchemaError(f"无法解析正确率：{raw!r}")
    if isinstance(raw, (int, float)):
        value = float(raw)
        if not math.isfinite(value):
            raise SchemaError(f"无法解析正确率：{raw!r}")
        if value <= 1.0:
            value *= 100.0
    elif isinstance(raw, str):
        text = raw.strip()
        has_percent = text.endswith("%")
        if has_percent:
            text = text[:-1].strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise SchemaError(
                f"无法解析正确率：{raw!r}（支持 80%、80、0.8 三种写法）"
            ) from exc
        if not math.isfinite(value):
            raise SchemaError(f"无法解析正确率：{raw!r}")
        if not has_percent and value <= 1.0:
            value *= 100.0
    else:
        raise SchemaError(f"无法解析正确率：{raw!r}（类型 {type(raw).__name__}）")
    if not 0.0 <= value <= 100.0:
        raise SchemaError(f"正确率超出 0–100 范围：{value:g}%")
    return round(value, 1)


# ---------- 记录 1：study-timer 的学习段 ----------

@dataclass
class StudySession:
    """一段计时学习记录（study-timer log.json 的一条）。

    ``day`` 归属由 ``start`` 的日期决定 —— 跨午夜的学习段归到开始那天，
    与人的直觉一致（「昨晚学到凌晨」算昨天的投入）。
    """

    start: datetime
    end: datetime
    minutes: float
    subject: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise SchemaError(f"StudySession.end 不能早于 start：{self.start} → {self.end}")
        if self.minutes < 0:
            raise SchemaError(f"StudySession.minutes 不能为负：{self.minutes}")
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise SchemaError("StudySession.subject 必须是非空字符串")
        self.subject = self.subject.strip()

    @property
    def day(self) -> date:
        """学习段归属的日期（取开始时间的日期）。"""
        return self.start.date()

    def to_dict(self) -> dict[str, Any]:
        """序列化为 study-timer 同构的 dict（时间用 ISO 串）。"""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "minutes": self.minutes,
            "subject": self.subject,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> StudySession:
        """从 dict 反序列化；任何字段问题都抛带字段名的 SchemaError。"""
        if not isinstance(data, dict):
            raise SchemaError(f"StudySession 应为 JSON 对象，得到 {type(data).__name__}")
        try:
            raw_start, raw_end = data["start"], data["end"]
            raw_minutes, raw_subject = data["minutes"], data["subject"]
        except KeyError as exc:
            raise SchemaError(f"StudySession 缺少字段：{exc.args[0]}") from exc
        note = data.get("note")
        return cls(
            start=_parse_datetime(raw_start, "start"),
            end=_parse_datetime(raw_end, "end"),
            minutes=_parse_number(raw_minutes, "minutes"),
            subject=_require_text(raw_subject, "subject"),
            note=note if isinstance(note, str) else "",
        )


# ---------- 记录 2：日报里的三件事 ----------

@dataclass
class TaskItem:
    """「明日三件事」的一条，带回看状态。

    状态语义（与日报母版对齐）：
    ``pending`` 新计划未回看 · ``done`` 完成 · ``partial`` 部分完成 ·
    ``missed`` 回看时仍未动（母版：保持 ``[ ]`` 即 missed）。
    """

    text: str
    status: TaskStatus = "pending"

    def __post_init__(self) -> None:
        self.text = _require_text(self.text, "TaskItem.text")
        if self.status not in TASK_STATUSES:
            raise SchemaError(
                f"TaskItem.status 非法：{self.status!r}（期望 {'/'.join(TASK_STATUSES)}）"
            )

    @property
    def counted(self) -> bool:
        """是否计入执行率分母 —— pending 还没到回看时点，计进去会稀释执行率。"""
        return self.status != "pending"

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "status": self.status}

    @classmethod
    def from_dict(cls, data: Any) -> TaskItem:
        if not isinstance(data, dict):
            raise SchemaError(f"TaskItem 应为 JSON 对象，得到 {type(data).__name__}")
        if "text" not in data:
            raise SchemaError("TaskItem 缺少字段：text")
        return cls(text=data["text"], status=data.get("status", "pending"))


# ---------- 记录 3：自测条目 ----------

@dataclass
class SelfTest:
    """一次章节自测 / 真题的成绩条目。

    ``accuracy`` 统一存 0–100 的百分数（人读的口径）；
    人类输入的 ``0.8`` 之类由 :func:`parse_accuracy` 在入口处转换，
    存储层永远只见到百分数，避免两种口径混存。
    """

    subject: str
    section: str
    accuracy: float
    day: date
    source: str = "manual"  # manual = log-test 录入；report = 从日报解析

    def __post_init__(self) -> None:
        self.subject = _require_text(self.subject, "SelfTest.subject")
        self.section = _require_text(self.section, "SelfTest.section")
        if isinstance(self.accuracy, bool) or not isinstance(self.accuracy, (int, float)):
            raise SchemaError(f"SelfTest.accuracy 必须是数字，得到 {self.accuracy!r}")
        self.accuracy = float(self.accuracy)
        if not 0.0 <= self.accuracy <= 100.0:
            raise SchemaError(f"SelfTest.accuracy 超出 0–100：{self.accuracy}")
        if not isinstance(self.day, date) or isinstance(self.day, datetime):
            raise SchemaError(f"SelfTest.day 必须是 date，得到 {self.day!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "section": self.section,
            "accuracy": self.accuracy,
            "date": self.day.isoformat(),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SelfTest:
        if not isinstance(data, dict):
            raise SchemaError(f"SelfTest 应为 JSON 对象，得到 {type(data).__name__}")
        missing = [k for k in ("subject", "section", "accuracy", "date") if k not in data]
        if missing:
            raise SchemaError(f"SelfTest 缺少字段：{', '.join(missing)}")
        try:
            day = date.fromisoformat(str(data["date"]))
        except ValueError as exc:
            raise SchemaError(f"SelfTest.date 不是合法日期：{data['date']!r}") from exc
        return cls(
            subject=data["subject"],
            section=data["section"],
            accuracy=_parse_number(data["accuracy"], "accuracy"),
            day=day,
            source=str(data.get("source", "manual")),
        )


# ---------- 记录 4：整份日报 ----------

@dataclass
class DailyReport:
    """一份结构化日报：日期 + 三件事 + 自测清单 + 可选自由文本。

    ``free_text`` 保留「今日成果 / 一句话点评」等非结构化小节原文，
    供 RQ3 的日志文本标注直接取用（计划书：文本反思保留原样）。
    """

    day: date
    tasks: list[TaskItem] = field(default_factory=list)
    self_tests: list[SelfTest] = field(default_factory=list)
    free_text: str = ""
    source: str = ""  # 来源文件路径，便于溯源与排错

    def __post_init__(self) -> None:
        if not isinstance(self.day, date) or isinstance(self.day, datetime):
            raise SchemaError(f"DailyReport.day 必须是 date，得到 {self.day!r}")
        for item in self.tasks:
            if not isinstance(item, TaskItem):
                raise SchemaError(f"DailyReport.tasks 应为 TaskItem 列表，得到 {type(item).__name__}")
        for test in self.self_tests:
            if not isinstance(test, SelfTest):
                raise SchemaError(f"DailyReport.self_tests 应为 SelfTest 列表，得到 {type(test).__name__}")

    @property
    def execution_rate(self) -> float | None:
        """三件事执行率：done / 已回看数；一条都没回看时为 None（而非 0）。"""
        counted = [t for t in self.tasks if t.counted]
        if not counted:
            return None
        done = sum(1 for t in counted if t.status == "done")
        return done / len(counted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day.isoformat(),
            "tasks": [t.to_dict() for t in self.tasks],
            "self_tests": [t.to_dict() for t in self.self_tests],
            "free_text": self.free_text,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DailyReport:
        if not isinstance(data, dict):
            raise SchemaError(f"DailyReport 应为 JSON 对象，得到 {type(data).__name__}")
        missing = [k for k in ("date", "tasks", "self_tests") if k not in data]
        if missing:
            raise SchemaError(f"DailyReport 缺少字段：{', '.join(missing)}")
        try:
            day = date.fromisoformat(str(data["date"]))
        except ValueError as exc:
            raise SchemaError(f"DailyReport.date 不是合法日期：{data['date']!r}") from exc
        return cls(
            day=day,
            tasks=[TaskItem.from_dict(t) for t in data["tasks"]],
            self_tests=[SelfTest.from_dict(t) for t in data["self_tests"]],
            free_text=str(data.get("free_text", "")),
            source=str(data.get("source", "")),
        )


# ---------- JSON 读写 ----------

def write_json(path: str | Path, payload: Any) -> None:
    """写 JSON（UTF-8、带缩进、中文不转义），父目录不存在则创建。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> Any:
    """读 JSON；文件缺失 / 损坏都转成带路径的 SchemaError。"""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaError(f"无法读取 {target}：{exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{target} 不是合法 JSON：{exc}") from exc


_T = TypeVar("_T")


def load_records(path: str | Path, factory: type[_T]) -> list[_T]:
    """读一个「对象数组」JSON 并逐条经 ``factory.from_dict`` 校验。

    文件不存在返回空列表 —— 研究早期数据尚未积累不算错误。
    """
    target = Path(path)
    if not target.exists():
        return []
    raw = read_json(target)
    if not isinstance(raw, list):
        raise SchemaError(f"{target} 顶层应为数组，得到 {type(raw).__name__}")
    records: list[_T] = []
    for index, item in enumerate(raw, 1):
        try:
            records.append(factory.from_dict(item))  # type: ignore[attr-defined]
        except SchemaError as exc:
            raise SchemaError(f"{target} 第 {index} 条记录无效：{exc}") from exc
    return records


def save_records(path: str | Path, records: Iterable[Any]) -> None:
    """把带 ``to_dict`` 的记录列表落盘。"""
    write_json(path, [r.to_dict() for r in records])
