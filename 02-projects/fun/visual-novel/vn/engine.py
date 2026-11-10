"""引擎主循环：打字机演出、选项菜单、分支跳转、存读档命令、结局判定。

「继续」提示处可输入：``s N`` 存档、``l N`` 读档、``h`` 历史回看、``+/-``
调速、``q`` 退出（打字中按任意键跳过）。结局：``@end 名`` 直接指定，
``@end`` 则按 ``@ending ... when 条件`` 阈值规则自上而下取首个命中项。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .render import Renderer
from .script import (Choice, Dialogue, End, Fx, If, Jump, Label, Narration,
                     Scene, Script, SetVar)
from .state import HistoryEntry, SaveError, State

__all__ = ["EngineError", "QuitGame", "EngineConfig", "Engine", "DEFAULT_ENDING"]

DEFAULT_ENDING = "剧终"
_SPEED_STEP = 1.5
_MIN_CPS = 2.0
_MAX_CPS = 400.0
_CMD_RE = re.compile(r"^([slSL])\s*(\d+)$")


class EngineError(RuntimeError):
    """运行期剧本错误（解析期查不出的动态问题）。"""


class QuitGame(Exception):
    """玩家主动退出（内部信号）。"""


@dataclass
class EngineConfig:
    """引擎配置。"""
    cps: float = 30.0               # 打字机速度（字符/秒），<=0 为瞬时
    autoplay: bool = False          # 自动演示：免回车、自动选第一项
    show_fx: bool = True            # 是否渲染音效/演出标记
    save_dir: str = "output/saves"  # 存档槽目录
    banner: bool = True             # 开场是否渲染标题


class Engine:
    """一局游戏的驱动器：持有 Script + State + Renderer，跑到结局返回其名。"""

    def __init__(self, script: Script, renderer: Optional[Renderer] = None,
                 state: Optional[State] = None, config: Optional[EngineConfig] = None,
                 input_fn: Optional[Callable[[str], str]] = None,
                 key_poll: Optional[Callable[[], Optional[str]]] = None):
        self.script = script
        self.config = config or EngineConfig()
        self.renderer = renderer or Renderer(cps=self.config.cps)
        if key_poll is not None:
            self.renderer.key_poll = key_poll
        self.state = state or State(script_name=script.name)
        self._input = input_fn
        self._eof = False

    def _read(self, prompt: str) -> str:
        """读一行；EOF（管道到头）后转入静默自动继续，不再请求输入。"""
        if self.config.autoplay or self._eof:
            return ""
        try:
            if self._input is not None:
                return (self._input(prompt) or "").strip()
            return input(prompt).strip()
        except EOFError:
            self._eof = True
            return ""

    # ---- 主循环 ----------------------------------------------------------

    def run(self) -> Optional[str]:
        """执行到结局，返回结局名；玩家中途退出返回 None。"""
        r = self.renderer
        if self.config.banner:
            src = self.script.source
            name = "内联脚本" if src.startswith("<") else re.split(r"[\\/]", src)[-1]
            r.banner(self.script.name, f"剧本来源：{name}")
        try:
            while 0 <= self.state.line_index < len(self.script.lines):
                self._step()
        except QuitGame:
            r.notice("已退出本局（进度未丢失，随时可以从存档读回）")
            return None
        except KeyboardInterrupt:
            r.write()
            r.notice("已中断")
            return None
        if self.state.ending is None:  # 剧本没写 @end：按阈值兜底判定
            self._finish(None, lineno=0)
        return self.state.ending

    def _step(self) -> None:
        """执行当前行并推进/跳转 line_index。"""
        line = self.script.lines[self.state.line_index]
        nxt = self.state.line_index + 1

        if isinstance(line, Label):
            pass
        elif isinstance(line, Scene):
            self.state.scene = line.title
            self.renderer.scene(line.title)
            self.state.record(HistoryEntry("scene", scene=line.title, lineno=line.lineno))
        elif isinstance(line, SetVar):
            self.state.apply(line.name, line.op, line.value)
        elif isinstance(line, Jump):
            nxt = self._target(line.label, line.lineno)
        elif isinstance(line, If):
            if self.state.satisfies(line.condition):
                nxt = self._target(line.label, line.lineno)
        elif isinstance(line, Dialogue):
            self.state.record(HistoryEntry("line", speaker=line.speaker,
                                           text=line.text, scene=self.state.scene,
                                           lineno=line.lineno))
            self.renderer.line(line.speaker, line.text)
            self._wait_continue()
        elif isinstance(line, Narration):
            self.state.record(HistoryEntry("narration", text=line.text,
                                           scene=self.state.scene, lineno=line.lineno))
            self.renderer.narration(line.text)
            self._wait_continue()
        elif isinstance(line, Choice):
            nxt = self._do_choice(line)
        elif isinstance(line, Fx):
            if self.config.show_fx:
                self.renderer.fx(line.kind, line.name)
            self.state.record(HistoryEntry("fx", text=f"{line.kind}:{line.name}",
                                           lineno=line.lineno))
        elif isinstance(line, End):
            self._finish(line.ending, line.lineno)
            nxt = len(self.script.lines)  # 跳出主循环
        else:  # pragma: no cover - 未知行类型
            raise EngineError(f"未知行类型 {type(line).__name__}（第 {line.lineno} 行）")
        self.state.line_index = nxt

    def _target(self, label: str, lineno: int) -> int:
        if label not in self.script.labels:
            raise EngineError(f"第 {lineno} 行：标签 {label!r} 不存在（剧本应先通过解析）")
        return self.script.labels[label]

    # ---- 选项 ------------------------------------------------------------

    def _do_choice(self, line: Choice) -> int:
        visible = [o for o in line.options if self.state.satisfies(o.condition)]
        if not visible:
            raise EngineError(
                f"第 {line.lineno} 行：所有选项的条件都不满足——"
                "请至少保留一个无条件选项作为兜底")
        r = self.renderer
        r.choices([o.text for o in visible])

        picked = visible[0] if self.config.autoplay else None
        while picked is None:
            raw = self._read(r.choice_prompt(len(visible)))
            if raw.lower() in ("q", "quit", "exit"):
                raise QuitGame
            if raw == "":
                picked = visible[0]  # 空回车 = 选第 1 项
                break
            try:
                idx = int(raw)
            except ValueError:
                r.warn("请输入选项编号")
                continue
            if 1 <= idx <= len(visible):
                picked = visible[idx - 1]
            else:
                r.warn(f"编号超出范围 1-{len(visible)}")

        r.chosen(picked.text)
        self.state.record(HistoryEntry(
            "choice", choice={"index": visible.index(picked) + 1, "text": picked.text},
            scene=self.state.scene, lineno=line.lineno))
        return self._target(picked.label, line.lineno)

    def _wait_continue(self) -> None:
        if self.config.autoplay or self._eof:
            return
        r = self.renderer
        while True:
            raw = self._read(r.continue_prompt())
            cmd = raw.strip()
            if cmd == "":
                return
            low = cmd.lower()
            if low in ("q", "quit", "exit"):
                raise QuitGame
            if low == "h":
                r.history_view(self.state.history)
                continue
            if cmd in ("+", "="):
                self._speed(True)
                continue
            if cmd == "-":
                self._speed(False)
                continue
            m = _CMD_RE.match(cmd)
            if m:
                self._slot_command(m.group(1).lower(), int(m.group(2)))
                continue
            r.warn("命令无效：可用 s N / l N / h / +/- / q，或直接回车继续")

    def _speed(self, up: bool) -> None:
        step = _SPEED_STEP if up else 1 / _SPEED_STEP
        self.renderer.cps = min(_MAX_CPS, max(_MIN_CPS, self.renderer.cps * step))
        self.renderer.notice(f"打字速度 {self.renderer.cps:.0f} 字符/秒")

    def _slot_command(self, op: str, slot: int) -> None:
        r = self.renderer
        try:
            if op == "s":
                path = self.state.save_to(slot, self.config.save_dir)
                r.notice(f"已存档 → {path}")
            else:
                loaded = State.load_from(slot, self.config.save_dir,
                                         expect_script=self.script.name)
                self.state = loaded
                r.notice(f"已读档 ← 第 {slot} 槽（{loaded.scene or '开场'}）")
        except SaveError as exc:
            r.warn(str(exc))

    # ---- 结局 ------------------------------------------------------------

    def evaluate_endings(self) -> str:
        """按 @ending 阈值规则取首个命中；全部落空返回默认结局。"""
        for rule in self.script.endings:
            if self.state.satisfies(rule.condition):
                return rule.name
        return DEFAULT_ENDING

    def _finish(self, explicit: Optional[str], lineno: int) -> None:
        name = explicit or self.evaluate_endings()
        self.state.ending = name
        self.state.line_index = len(self.script.lines)
        self.state.record(HistoryEntry("ending", text=name, lineno=lineno))
        self.renderer.ending(name)
