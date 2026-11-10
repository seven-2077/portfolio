"""数据摄入：study-timer JSON 与日报 Markdown → 按日对齐的研究就绪结构。

三路数据在这里汇合成 :class:`DayRecord`（某日 = session 数组 + 日报 + 自测），
是后续所有分析（周汇总、滞后相关、执行率时序）的唯一入口。

为什么解析失败要带行号：日报是人（和 LLM）写的，格式漂移在所难免；
没有行号的报错等于让人通读全文找茬，摩擦一高就不会有人修数据了。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .schema import (
    TASK_STATUSES,
    DailyReport,
    SchemaError,
    SelfTest,
    StudySession,
    TaskItem,
    load_records,
    parse_accuracy,
)

__all__ = [
    "ParseError",
    "DaySessions",
    "DayRecord",
    "load_sessions",
    "load_selftests",
    "parse_report",
    "ingest_all",
]


class ParseError(ValueError):
    """源数据解析失败；消息自带「路径:行 N: 原因」便于直接定位。"""

    def __init__(self, message: str, *, path: Path | str | None = None,
                 line: int | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.line = line
        prefix = ""
        if self.path is not None:
            prefix = str(self.path)
        if line is not None:
            prefix = f"{prefix}:行 {line}" if prefix else f"行 {line}"
        super().__init__(f"{prefix}: {message}" if prefix else message)


# ---------- 记录 1：study-timer ----------

@dataclass
class DaySessions:
    """某一天的全部学习段 + 按科目聚合的派生视图。"""

    day: date
    sessions: list[StudySession] = field(default_factory=list)

    @property
    def total_minutes(self) -> float:
        """当日总分钟数，四舍五入到 0.1 —— 与 study-timer 的显示口径一致。"""
        return round(sum(s.minutes for s in self.sessions), 1)

    def minutes_by_subject(self) -> dict[str, float]:
        """科目 → 分钟数，按投入从多到少排（报告直接可打印）。"""
        bucket: dict[str, float] = {}
        for s in self.sessions:
            bucket[s.subject] = round(bucket.get(s.subject, 0.0) + s.minutes, 1)
        return dict(sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0])))


def load_sessions(timer_json_path: str | Path) -> dict[date, DaySessions]:
    """读 study-timer 的 log.json，按日聚合（日 → 当日学习段）。

    - 文件不存在 → 空 dict：study-timer 刚起步没跑出数据不算错误，
      研究早期「某天没数据」本身就是数据的一部分；
    - JSON 损坏 / 结构不对 → :class:`ParseError`（静默返回空会丢整段积累）。
    """
    path = Path(timer_json_path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ParseError(f"log.json 不是合法 JSON：{exc}", path=path) from exc
    except OSError as exc:
        raise ParseError(f"无法读取文件：{exc}", path=path) from exc
    if not isinstance(raw, list):
        raise ParseError(
            f"log.json 顶层应为数组（study-timer 的记录列表），"
            f"得到 {type(raw).__name__}",
            path=path,
        )
    sessions: list[StudySession] = []
    for index, item in enumerate(raw, 1):
        try:
            sessions.append(StudySession.from_dict(item))
        except SchemaError as exc:
            raise ParseError(f"第 {index} 条记录无效：{exc}", path=path) from exc
    buckets: dict[date, list[StudySession]] = {}
    for session in sessions:
        buckets.setdefault(session.day, []).append(session)
    return {
        day: DaySessions(day=day, sessions=items)
        for day, items in sorted(buckets.items())
    }


def load_selftests(path: str | Path) -> list[SelfTest]:
    """读手动录入的自测成绩（``selftest.json``）；文件不存在返回空列表。"""
    return load_records(path, SelfTest)


# ---------- 记录 2：日报 Markdown ----------

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
#: checkbox 行：`- [x] 事项` / `- [-] 事项` / `- [ ] 事项`（允许缩进）
CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX-])\]\s*(.*?)\s*$")
#: 母版规定的行内状态注释：`# status: pending`
STATUS_COMMENT_RE = re.compile(r"#\s*status:\s*([A-Za-z]+)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+")

SECTION_TASKS = "明日三件事"
SECTION_SELFTEST = "今日自测"

_MARKER_STATUS = {"x": "done", "X": "done", "-": "partial", " ": "missed"}


def _resolve_day(path: Path, lines: list[str]) -> date:
    """确定日报日期：优先文件名（``2026-11-04-日报.md``），再扫正文首个日期。

    为什么允许正文日期：日报常以 ``日报.md`` 或周记名落盘，日期只在正文里；
    两者都没有才报错 —— 没有日期的日报无法对齐 session 序列，必须拦下。
    """
    match = DATE_RE.search(path.name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass  # 文件名里的日期不合法，继续尝试正文
    for index, line in enumerate(lines, 1):
        match = DATE_RE.search(line)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                continue
    raise ParseError("文件名与正文均未找到 YYYY-MM-DD 形式的日期", path=path)


def _split_sections(
    lines: list[str],
) -> list[tuple[str, int, list[tuple[int, str]]]]:
    """按 ``###`` 标题切小节。

    返回 ``(小节名, 标题行号, [(全局行号, 行文本), ...])``；
    保留全局行号是为了报错时能指回原文件的真实行。
    """
    sections: list[tuple[str, int, list[tuple[int, str]]]] = []
    name: str | None = None
    heading_line = 0
    body: list[tuple[int, str]] = []
    for index, line in enumerate(lines, 1):
        if HEADING_RE.match(line):
            if name is not None:
                sections.append((name, heading_line, body))
            name = line.lstrip("#").strip()
            heading_line, body = index, []  # type: ignore[assignment]
        elif name is not None:
            body.append((index, line))
    if name is not None:
        sections.append((name, heading_line, body))
    return sections


def _find_section(
    sections: list[tuple[str, int, list[tuple[int, str]]]], prefix: str
) -> tuple[int, list[tuple[int, str]]] | None:
    """按标题前缀找小节（容忍 ``### 今日自测（11-04）`` 这类后缀）。"""
    for name, heading_line, body in sections:
        if name.startswith(prefix):
            return heading_line, body
    return None


def _task_status(marker: str, raw_text: str, path: Path, line: int) -> str:
    """从 checkbox 标记 + 行内注释推断状态。

    优先级：``# status: xxx`` 注释 > 标记本身 —— 母版要求新计划写
    ``[ ] # status: pending``，若只看标记会把「还没回看的新计划」误判成 missed。
    """
    match = STATUS_COMMENT_RE.search(raw_text)
    if match:
        status = match.group(1).lower()
        if status not in TASK_STATUSES:
            raise ParseError(
                f"未知 status：{match.group(1)!r}"
                f"（期望 {'/'.join(TASK_STATUSES)}）",
                path=path, line=line,
            )
        return status
    return _MARKER_STATUS[marker]


def _parse_tasks(
    heading_line: int,
    body: list[tuple[int, str]],
    path: Path,
) -> list[TaskItem]:
    """解析「明日三件事」小节里的 checkbox 行。"""
    tasks: list[TaskItem] = []
    for index, line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue  # 空行与小节内的说明性文字不是数据
        if not stripped.startswith("-"):
            continue  # 普通散文段落（母版要求的解释文字），不是数据
        match = CHECKBOX_RE.match(line)
        if not match:
            raise ParseError(
                "不是合法的 checkbox 行（期望 - [x] / - [-] / - [ ]）",
                path=path, line=index,
            )
        marker, raw_text = match.group(1), match.group(2)
        status = _task_status(marker, raw_text, path, index)
        text = STATUS_COMMENT_RE.sub("", raw_text).strip()
        if not text:
            raise ParseError("checkbox 行缺少事项描述", path=path, line=index)
        tasks.append(TaskItem(text=text, status=status))
    if not tasks:
        # 空小节多半是模板没填就交了 —— 宁可报错，也不让空数据溜进研究序列
        raise ParseError(
            f"「{SECTION_TASKS}」小节内没有任何 checkbox 行",
            path=path, line=heading_line,
        )
    return tasks


def _parse_self_tests(
    heading_line: int,
    body: list[tuple[int, str]],
    path: Path,
    day: date,
) -> list[SelfTest]:
    """解析「今日自测」小节：``科目 | 章节 | 正确率``，或「今日无自测」。

    该节只允许这两类内容（母版明文约束），所以非空且不符合格式的行一律
    报错而不是跳过 —— 静默跳过等于把真实自测成绩弄丢，是研究数据的硬伤。
    """
    tests: list[SelfTest] = []
    for index, line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "无自测" in stripped:
            continue  # 母版：没有自测就写「今日无自测」
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ParseError(
                "自测行格式应为「科目 | 章节 | 正确率」，"
                "如 408 | 数据结构第六章选择 15 题 | 80%",
                path=path, line=index,
            )
        try:
            accuracy = parse_accuracy(parts[2])
        except SchemaError as exc:
            raise ParseError(
                f"正确率无法解析：{exc}", path=path, line=index
            ) from exc
        tests.append(SelfTest(
            subject=parts[0], section=parts[1], accuracy=accuracy,
            day=day, source="report",
        ))
    return tests


def parse_report(markdown_path: str | Path) -> DailyReport:
    """解析一份日报 Markdown → :class:`DailyReport`。

    必备结构（对齐母版）：可定位的日期、``### 明日三件事``、``### 今日自测``；
    其余小节（今日成果、一句话点评等）原文收进 ``free_text`` 供 RQ3 使用。
    """
    path = Path(markdown_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"无法读取文件：{exc}", path=path) from exc
    lines = text.splitlines()
    if not lines:
        raise ParseError("空文件", path=path, line=1)

    day = _resolve_day(path, lines)
    sections = _split_sections(lines)

    tasks_section = _find_section(sections, SECTION_TASKS)
    if tasks_section is None:
        raise ParseError(
            f"缺少「### {SECTION_TASKS}」小节", path=path, line=len(lines)
        )
    tests_section = _find_section(sections, SECTION_SELFTEST)
    if tests_section is None:
        raise ParseError(
            f"缺少「### {SECTION_SELFTEST}」小节（没有自测也应写「今日无自测」）",
            path=path, line=len(lines),
        )

    tasks = _parse_tasks(tasks_section[0], tasks_section[1], path)
    self_tests = _parse_self_tests(tests_section[0], tests_section[1], path, day)

    # 自由文本 = 除两个结构化小节外的所有原文（RQ3 的语料入口）
    free_parts: list[str] = []
    for name, _heading_line, body in sections:
        if name.startswith(SECTION_TASKS) or name.startswith(SECTION_SELFTEST):
            continue
        free_parts.append(f"### {name}")
        free_parts.extend(line for _i, line in body)
    free_text = "\n".join(free_parts).strip()

    return DailyReport(
        day=day, tasks=tasks, self_tests=self_tests,
        free_text=free_text, source=str(path),
    )


# ---------- 汇总：按日对齐 ----------

def _collect_reports(root: Path) -> list[Path]:
    """收集日报：``<data_dir>/*.md`` 与 ``<data_dir>/reports/*.md``，按文件名排序。"""
    files = list(root.glob("*.md")) + list((root / "reports").glob("*.md"))
    return sorted(files, key=lambda p: p.name)


@dataclass
class DayRecord:
    """研究就绪的「一天」：session 数组 + 日报 + 当日全部自测。

    为什么日报与手动自测要合并去重：同一次自测可能既被 AI 写进日报、
    又被 ``log-test`` 手动录了一条，不去重会让周报的平均正确率重复计数。
    精确匹配（日期+科目+章节+正确率）是保守做法，宁可漏去重也不错去重。
    """

    day: date
    sessions: list[StudySession] = field(default_factory=list)
    report: DailyReport | None = None
    self_tests: list[SelfTest] = field(default_factory=list)

    @property
    def total_minutes(self) -> float:
        """当日总分钟数（0.1 分钟精度）。"""
        return round(sum(s.minutes for s in self.sessions), 1)


def _same_test(a: SelfTest, b: SelfTest) -> bool:
    """两次自测是否是同一次（精确匹配，用于跨源去重）。"""
    return (a.day == b.day and a.subject == b.subject
            and a.section == b.section and a.accuracy == b.accuracy)


def ingest_all(
    data_dir: str | Path, log_path: str | Path | None = None
) -> list[DayRecord]:
    """把 data_dir 下三路数据按日对齐，返回按日期升序的 :class:`DayRecord` 列表。

    data_dir 的约定布局（缺哪路都行，缺的那路按空处理）::

        data_dir/
          log.json        # study-timer 记录（或用 log_path 指向别处）
          reports/*.md    # 每日学习日报
          *.md            # 也接受直接放在根下的日报
          selftest.json   # log-test 手动录入的自测

    某日只有 session 没日报（或反之）也会产出 DayRecord —— 「哪天缺什么」
    本身就是要展示的研究信息，不能因为缺日报就把那天的时长也丢掉。
    """
    root = Path(data_dir)
    sessions = load_sessions(
        Path(log_path) if log_path is not None else root / "log.json"
    )
    manual_tests = load_selftests(root / "selftest.json")

    reports: dict[date, DailyReport] = {}
    for md in _collect_reports(root):
        report = parse_report(md)
        # 同日多份日报：保留第一份（文件名排序后最早），不中断整个 ingest；
        # 重复本身就是数据质量问题，交给使用者从文件名发现。
        reports.setdefault(report.day, report)

    by_day: dict[date, DayRecord] = {}
    for day in sorted(set(sessions) | set(reports)
                      | {t.day for t in manual_tests}):
        day_sessions = sessions.get(day)
        by_day[day] = DayRecord(
            day=day,
            sessions=list(day_sessions.sessions) if day_sessions else [],
            report=reports.get(day),
            self_tests=[t for t in manual_tests if t.day == day],
        )

    # 日报里的自测并入当日清单（已存在的精确重复跳过）
    for day, record in by_day.items():
        if record.report is None:
            continue
        for test in record.report.self_tests:
            if not any(_same_test(test, existing)
                       for existing in record.self_tests):
                record.self_tests.append(test)
        record.self_tests.sort(key=lambda t: (t.subject, t.section))

    return [by_day[day] for day in sorted(by_day)]
