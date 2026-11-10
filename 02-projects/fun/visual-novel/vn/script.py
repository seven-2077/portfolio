"""剧本脚本解析器：纯文本 DSL -> 结构化 Script 对象。

一行为一种东西：``@指令`` / ``说话人: 台词`` / ``|旁白`` / ``- 选项``；
空行与 ``#`` 整行注释忽略，反斜杠转义（\\: \\n \\t \\\\）处处生效。
完整文法与教程见 README《剧本格式完整教程》，错误一律带行号抛 ScriptError。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "ScriptError", "Comparison", "VarRef", "Condition",
    "Dialogue", "Narration", "Scene", "SetVar", "Jump", "If",
    "Option", "Choice", "Label", "End", "Fx", "EndingRule", "Script",
    "parse_script", "parse_condition",
]


class ScriptError(ValueError):
    """剧本格式错误，携带来源与行号。"""

    def __init__(self, message: str, source: str = "<string>", lineno: int = 0):
        self.source = source
        self.lineno = lineno
        self.message = message
        super().__init__(f"{source}:{lineno}: {message}" if lineno else f"{source}: {message}")


@dataclass(frozen=True)
class VarRef:
    """条件右值引用另一个变量。"""
    name: str


@dataclass(frozen=True)
class Comparison:
    """一次比较：变量 <op> 字面量或变量。"""
    var: str
    op: str
    value: Any  # 常量（int/float/str/bool）或 VarRef


@dataclass(frozen=True)
class Condition:
    """条件表达式：Comparison 与 'and'/'or' 交错的 token 序列，and 优先于 or。"""
    tokens: tuple
    raw: str = ""


_CMP_RE = re.compile(r"^(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+)$", re.S)
_IDENT_RE = re.compile(r"^[^\W\d]\w*$", re.U)
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _parse_rhs(text: str, source: str, lineno: int) -> Any:
    """条件右值：引号串 -> 字符串；数字/bool -> 常量；裸标识符 -> 变量引用。"""
    text = text.strip()
    if not text:
        raise ScriptError("比较运算缺少右值", source, lineno)
    if text.startswith('"'):
        return _parse_quoted(text, source, lineno)[0]
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if _NUM_RE.match(text):
        return float(text) if "." in text else int(text)
    if _IDENT_RE.match(text):
        return VarRef(text)
    raise ScriptError(
        f"比较右值 {text!r} 无法识别：字符串请加双引号", source, lineno)


def parse_condition(text: str, source: str = "<string>", lineno: int = 0) -> Condition:
    """解析 `a >= 1 and b == x or c != 2` 形式的条件表达式。"""
    raw = text.strip()
    if not raw:
        raise ScriptError("条件表达式为空", source, lineno)
    parts = re.split(r"\s+(and|or)\s+", raw)   # 奇数位必为连接词
    tokens: list = []
    for i, part in enumerate(parts):
        part = part.strip()
        if i % 2 == 1:
            tokens.append(part)
            continue
        if not part:
            raise ScriptError(f"条件表达式 {raw!r} 语法错误", source, lineno)
        m = _CMP_RE.match(part)
        if not m:
            raise ScriptError(
                f"条件 {part!r} 格式错误，应形如 `affection >= 3`", source, lineno)
        var, op, rhs = m.group(1), m.group(2), m.group(3).strip()
        tokens.append(Comparison(var, op, _parse_rhs(rhs, source, lineno)))
    if tokens and tokens[0] in ("and", "or"):
        raise ScriptError("条件表达式以连接词开头", source, lineno)
    if tokens and tokens[-1] in ("and", "or"):
        raise ScriptError("条件表达式以连接词结尾", source, lineno)
    if len(tokens) % 2 == 0:
        raise ScriptError(f"条件表达式 {raw!r} 语法错误", source, lineno)
    return Condition(tuple(tokens), raw)


# --------------------------------------------------------------------- 行类型


@dataclass(frozen=True)
class Dialogue:
    """台词行：说话人 + 台词。"""
    speaker: str
    text: str
    lineno: int


@dataclass(frozen=True)
class Narration:
    """旁白行。"""
    text: str
    lineno: int


@dataclass(frozen=True)
class Scene:
    """场景切换。"""
    title: str
    lineno: int


@dataclass(frozen=True)
class SetVar:
    """变量赋值：name op value，op 属于 = += -=。"""
    name: str
    op: str
    value: Any
    lineno: int


@dataclass(frozen=True)
class Jump:
    """无条件跳转。"""
    label: str
    lineno: int


@dataclass(frozen=True)
class If:
    """条件跳转。"""
    condition: Condition
    label: str
    lineno: int


@dataclass(frozen=True)
class Option:
    """一个选项：可见性条件（可无）+ 文本 + 跳转目标。"""
    text: str
    label: str
    condition: Optional[Condition] = None
    lineno: int = 0


@dataclass(frozen=True)
class Choice:
    """选项块。"""
    options: tuple
    lineno: int


@dataclass(frozen=True)
class Label:
    """标签定义（引擎执行时为 no-op）。"""
    name: str
    lineno: int


@dataclass(frozen=True)
class End:
    """结束：ending 为 None 时按阈值规则判定。"""
    ending: Optional[str] = None
    lineno: int = 0


@dataclass(frozen=True)
class Fx:
    """音效/演出标记（预留，仅记录与提示）。"""
    kind: str  # sfx / bgm / anim
    name: str
    lineno: int = 0


@dataclass(frozen=True)
class EndingRule:
    """结局阈值规则：condition 命中则该结局生效。"""
    name: str
    condition: Condition
    lineno: int = 0


def _unescape_core(text: str, source: str, lineno: int) -> str:
    """处理反斜杠转义；行尾孤立反斜杠报错。"""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            raise ScriptError("行尾出现孤立的反斜杠（转义不完整）", source, lineno)
        nxt = text[i + 1]
        if nxt == "n":
            out.append("\n")
        elif nxt == "t":
            out.append("\t")
        else:
            out.append(nxt)  # \\ -> \，\: -> :，\其他 -> 其他
        i += 2
    return "".join(out)


def _parse_quoted(text: str, source: str, lineno: int) -> tuple:
    """解析双引号字符串，返回 (值, 剩余文本)。支持 \\" \\n \\t \\ 消转义。"""
    assert text.startswith('"')
    out: list[str] = []
    i, n = 1, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            return "".join(out), text[i + 1:].strip()
        if ch == "\\":
            if i + 1 >= n:
                raise ScriptError("字符串以孤立反斜杠结尾", source, lineno)
            nxt = text[i + 1]
            out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    raise ScriptError("字符串引号未闭合", source, lineno)


def _parse_value(raw: str, source: str, lineno: int) -> Any:
    """@set 右值：引号串 / 数字 / true|false / 裸字符串（unescape）。"""
    raw = raw.strip()
    if not raw:
        raise ScriptError("@set 缺少赋值内容", source, lineno)
    if raw.startswith('"'):
        value, rest = _parse_quoted(raw, source, lineno)
        if rest:
            raise ScriptError(f"@set 值后有多余内容: {rest!r}", source, lineno)
        return value
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if _NUM_RE.match(raw):
        return float(raw) if "." in raw else int(raw)
    return _unescape_core(raw, source, lineno)


def _find_split(text: str, sep: str) -> tuple:
    """按最后一个 sep 拆分；找不到返回 (None, None)。"""
    idx = text.rfind(sep)
    if idx < 0:
        return None, None
    return text[:idx].strip(), text[idx + len(sep):].strip()


def _parse_option(body: str, source: str, lineno: int) -> Option:
    left, label = _find_split(body, "->")
    if left is None:
        raise ScriptError(f"选项 {body!r} 缺少 `-> 跳转标签`", source, lineno)
    if not label:
        raise ScriptError("选项的跳转标签为空", source, lineno)
    condition = None
    if left.startswith("["):
        close = left.find("]")
        if close < 0:
            raise ScriptError("选项条件的 `]` 未闭合", source, lineno)
        condition = parse_condition(left[1:close], source, lineno)
        left = left[close + 1:].strip()
    text = _unescape_core(left, source, lineno).strip()
    if not text:
        raise ScriptError("选项文本为空", source, lineno)
    return Option(text=text, label=label, condition=condition, lineno=lineno)


_DIRECTIVES = {
    "label", "jump", "if", "set", "scene", "choice",
    "end", "ending", "sfx", "bgm", "anim",
}


def parse_script(text: str, source: str = "<string>") -> "Script":
    """把剧本全文解析为 Script；任何格式错误抛 ScriptError（带行号）。"""
    lines: list = []
    labels: dict[str, int] = {}
    endings: list[EndingRule] = []
    pending_choice: Optional[list[Option]] = None   # 正在收集的选项块
    choice_lineno = 0
    jumps: list[tuple] = []  # (目标标签, 行号) 待校验

    def close_choice() -> None:
        nonlocal pending_choice
        if pending_choice is not None:
            if not pending_choice:
                raise ScriptError("@choice 块中没有任何选项", source, choice_lineno)
            lines.append(Choice(tuple(pending_choice), choice_lineno))
            pending_choice = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue  # 空行与注释忽略

        # --- 选项行（仅在 @choice 块内有效）
        if line.startswith("-") and len(line) > 1 and line[1].isspace():
            if pending_choice is None:
                raise ScriptError("选项行 `-` 必须位于 @choice 块内", source, lineno)
            pending_choice.append(_parse_option(line[1:].strip(), source, lineno))
            continue

        # 非选项行会关闭正在收集的选项块
        if pending_choice is not None:
            close_choice()

        # --- 指令行
        if line.startswith("@"):
            parts = line[1:].split(None, 1)
            name = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""
            if name not in _DIRECTIVES:
                raise ScriptError(f"未知指令 @{name}", source, lineno)

            if name == "label":
                if not _IDENT_RE.match(rest or ""):
                    raise ScriptError(f"标签名 {rest!r} 非法（需为字母/下划线/中文开头的标识符）", source, lineno)
                if rest in labels:
                    raise ScriptError(f"标签 {rest!r} 重复定义", source, lineno)
                labels[rest] = len(lines)
                lines.append(Label(rest, lineno))
            elif name == "jump":
                if not rest:
                    raise ScriptError("@jump 缺少目标标签", source, lineno)
                jumps.append((rest, lineno))
                lines.append(Jump(rest, lineno))
            elif name == "if":
                cond_text, label = _find_split(rest, "->")
                if cond_text is None:
                    raise ScriptError("@if 缺少 `-> 目标标签`", source, lineno)
                if not label:
                    raise ScriptError("@if 的目标标签为空", source, lineno)
                jumps.append((label, lineno))
                lines.append(If(parse_condition(cond_text, source, lineno), label, lineno))
            elif name == "set":
                m = re.match(r"^(\w+)\s*(\+=|-=|=)\s*(.+)$", rest, re.S)
                if not m:
                    raise ScriptError(
                        f"@set 格式错误，应形如 `@set affection += 1`，实得: {rest!r}", source, lineno)
                lines.append(SetVar(m.group(1), m.group(2),
                                    _parse_value(m.group(3), source, lineno), lineno))
            elif name == "scene":
                if not rest:
                    raise ScriptError("@scene 缺少场景名", source, lineno)
                lines.append(Scene(_unescape_core(rest, source, lineno), lineno))
            elif name == "choice":
                if rest:
                    raise ScriptError("@choice 不接受参数（选项行以 `- ` 开头）", source, lineno)
                pending_choice = []
                choice_lineno = lineno
            elif name == "end":
                lines.append(End(_unescape_core(rest, source, lineno), lineno) if rest else End(None, lineno))
            elif name == "ending":
                if " when " not in rest:
                    raise ScriptError(
                        "@ending 需要 `when` 条件，应形如 `@ending 真结局 when affection >= 5`", source, lineno)
                ename, cond_text = rest.split(" when ", 1)
                ename = _unescape_core(ename.strip(), source, lineno)
                if not ename:
                    raise ScriptError("@ending 缺少结局名", source, lineno)
                endings.append(EndingRule(ename, parse_condition(cond_text, source, lineno), lineno))
            else:  # sfx / bgm / anim
                if not rest:
                    raise ScriptError(f"@{name} 缺少名称", source, lineno)
                lines.append(Fx(name, _unescape_core(rest, source, lineno), lineno))
            continue

        # --- 旁白行
        if line.startswith("|"):
            body = line[1:].lstrip()
            if not body:
                raise ScriptError("旁白行 `|` 后缺少文本", source, lineno)
            lines.append(Narration(_unescape_core(body, source, lineno), lineno))
            continue

        # --- 台词行（说话人: 台词）
        speaker = None
        for i, ch in enumerate(line):
            if ch == ":" and (i == 0 or line[i - 1] != "\\"):
                speaker = line[:i]
                body = line[i + 1:]
                break
        if speaker is None:
            raise ScriptError(
                f"无法识别的行: {line[:30]!r}（指令以 @ 开头、旁白以 | 开头、台词用 `说话人: 台词`）",
                source, lineno)
        speaker = _unescape_core(speaker, source, lineno).strip()
        if not speaker:
            raise ScriptError("台词行缺少说话人", source, lineno)
        lines.append(Dialogue(speaker, _unescape_core(body, source, lineno).strip(), lineno))

    if pending_choice is not None:
        close_choice()

    if not lines:
        raise ScriptError("剧本为空（没有任何有效行）", source, 0)

    # --- 后置校验：跳转目标必须存在
    for label, lineno in jumps:
        if label not in labels:
            raise ScriptError(f"跳转目标标签 {label!r} 不存在", source, lineno)

    return Script(lines=tuple(lines), labels=labels, endings=tuple(endings),
                  source=source, name=Path(source).stem if source != "<string>" else "untitled")


@dataclass
class Script:
    """解析后的剧本：行序列 + 标签表 + 结局阈值规则。"""
    lines: tuple
    labels: dict = field(default_factory=dict)
    endings: tuple = ()
    source: str = "<string>"
    name: str = "untitled"

    @classmethod
    def from_file(cls, path) -> "Script":
        p = Path(path)
        return parse_script(p.read_text(encoding="utf-8"), str(p))
