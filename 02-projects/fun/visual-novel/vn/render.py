"""终端渲染：场景框、名牌、台词区、选项编号、结局横幅，ANSI 配色。

打字机速度由 ``cps`` 控制（``<=0`` 瞬时）；按任意键跳过；``NO_COLOR`` 或
非 TTY 自动降级纯文本。Windows 用 msvcrt 轮询按键，POSIX 用 cbreak + select。
"""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from typing import Optional, TextIO

__all__ = ["Renderer", "KeyPoller", "strip_ansi", "enable_windows_ansi"]

ANSI_RE = re.compile(r"\u001b\[[0-9;]*m")

_CODE = {
    "reset": "\u001b[0m", "bold": "\u001b[1m", "dim": "\u001b[2m",
    "cyan": "\u001b[36m", "yellow": "\u001b[33m", "green": "\u001b[32m",
    "magenta": "\u001b[35m", "red": "\u001b[31m", "blue": "\u001b[34m",
    "bright": "\u001b[97m", "magenta_b": "\u001b[95m",
}


def strip_ansi(text: str) -> str:
    """去掉 ANSI 序列（用于落盘纯文本产物）。"""
    return ANSI_RE.sub("", text)


def enable_windows_ansi(stream: TextIO) -> bool:
    """在 Windows 控制台开启 VT 色彩处理；失败静默返回 False。"""
    if sys.platform != "win32" or not getattr(stream, "isatty", lambda: False)():
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11 if stream is sys.stdout else -12)
        mode = ctypes.c_uint32()
        return bool(k32.GetConsoleMode(handle, ctypes.byref(mode))
                    and k32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def display_width(text: str) -> int:
    """显示宽度：东亚全角 2 列；ambiguous（★◉─）按主流终端 1 列，保框线对齐。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


class KeyPoller:
    """非阻塞按键轮询：打字机期间按任意键跳过；非 TTY 恒返回 None。

    Windows 走 msvcrt；POSIX 进 cbreak + select，release() 恢复原模式。
    """

    def __init__(self, stream: Optional[TextIO] = None):
        self._stream = stream or sys.stdin
        self._is_tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._saved = None
        self._fd = None
        if self._is_tty and sys.platform != "win32":
            try:
                import termios
                import tty
                self._fd = self._stream.fileno()
                self._saved = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
            except Exception:
                self._fd = None

    def poll(self) -> Optional[str]:
        if not self._is_tty:
            return None
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    return msvcrt.getwch()
            else:
                import select
                if self._fd is None:
                    return None
                ready, _, _ = select.select([self._fd], [], [], 0)
                if ready:
                    os.read(self._fd, 1)
                    return " "
        except Exception:
            return None
        return None

    def release(self) -> None:
        """恢复终端（POSIX cbreak -> 原模式），可重复调用。"""
        if self._saved is not None and self._fd is not None:
            try:
                import termios
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
            except Exception:
                pass
            self._saved = None

    def close(self) -> None:
        self.release()


class Renderer:
    """把游戏事件画到终端流上；``key_poll`` 是可调用对象（如 KeyPoller.poll），
    打字期间返回非 None 表示按键跳过。"""

    def __init__(self, stream: Optional[TextIO] = None, color: Optional[bool] = None,
                 cps: float = 30.0, sleeper=time.sleep,
                 key_poll=None, interactive: bool = True):
        self.stream = stream or sys.stdout
        if color is None:
            color = ("NO_COLOR" not in os.environ
                     and bool(getattr(self.stream, "isatty", lambda: False)()))
        self.color = bool(color)
        if self.color and self.stream is not None:
            enable_windows_ansi(self.stream)
        self.cps = float(cps)
        self.sleeper = sleeper
        self.key_poll = key_poll
        self.interactive = interactive

    # ---- 基础输出 --------------------------------------------------------

    def _c(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(_CODE[c] for c in codes) + text + _CODE["reset"]

    def write(self, text: str = "") -> None:
        self.stream.write(text + "\n")
        self.stream.flush()

    def notice(self, text: str) -> None:
        """系统提示（存读档、速度、杂项）。"""
        self.write(self._c(f"  ※ {text}", "dim"))

    def warn(self, text: str) -> None:
        self.write(self._c(f"  ! {text}", "red"))

    # ---- 打字机 ----------------------------------------------------------

    def typewriter(self, text: str) -> None:
        """整段逐字输出（含换行控制）；期间按任意键立即完成；cps<=0 瞬时。"""
        self._typed_body(text)

    def _typed_body(self, text: str, codes: tuple = ()) -> None:
        """写正文（可选着色）+ 打字机节奏；按键可跳过。"""
        if self.cps <= 0 or not self.interactive:
            self.write(self._c(text, *codes))
            return
        interval = 1.0 / self.cps
        buf: list[str] = []
        for ch in text:
            if ch != "\n":
                self.sleeper(interval)
            buf.append(ch)
            self.stream.write(self._c(ch, *codes) if (self.color and codes) else ch)
            self.stream.flush()
            if self.key_poll is not None and self.key_poll() is not None:
                break
        else:
            self.stream.write("\n")
            self.stream.flush()
            return
        rest = text[len(buf):]  # 被按键打断：补上剩余文本
        self.write(self._c(rest, *codes))

    # ---- 场景与台词 ------------------------------------------------------

    def scene(self, title: str) -> None:
        """场景标题框（宽度按全角终端对齐）。"""
        bar = "─" * (display_width(title) + 6)
        self.write(self._c(f"╭{bar}╮", "cyan", "dim"))
        self.write(self._c(f"│  ◉ {title}  │", "cyan"))
        self.write(self._c(f"╰{bar}╯", "cyan", "dim"))
        self.write()

    def line(self, speaker: str, text: str) -> None:
        """台词区：名牌 + 逐字台词。"""
        name = self._c(f"【{speaker}】", "yellow", "bold")
        self.stream.write("  " + name + " ")
        self.stream.flush()
        self._typed_body(text)

    def narration(self, text: str) -> None:
        """旁白：无名牌、亮紫色调。"""
        self.stream.write("  ")
        self.stream.flush()
        self._typed_body(text, codes=("magenta_b",))

    # ---- 选项 ------------------------------------------------------------

    def choices(self, options: list, start: int = 1) -> None:
        """选项编号列表；options 为可见选项的文本列表。"""
        self.write()
        for i, opt in enumerate(options, start=start):
            num = self._c(f" {i}. ", "green", "bold")
            self.write("  " + num + opt)
        self.write()

    def choice_prompt(self, count: int) -> str:
        """选项输入提示文本（读取一行由引擎负责）。"""
        return self._c(f"  ▸ 请选择 [1-{count}]：", "green")

    def continue_prompt(self) -> str:
        """继续提示文本（回车继续 / 命令）。"""
        return self._c("  ⏎ 继续 · s N 存档 · l N 读档 · h 回看 · +/- 调速 · q 退出  ", "dim")

    def chosen(self, text: str) -> None:
        """回显已选定的选项（自动演示时留痕于 playthrough）。"""
        self.write(self._c(f"  ▸ {text}", "green"))

    # ---- 演出 / 结局 / 历史 ----------------------------------------------

    def fx(self, kind: str, name: str) -> None:
        """音效/演出标记（预留位，现阶段仅提示）。"""
        icon = {"sfx": "♪", "bgm": "♫", "anim": "✦"}.get(kind, "·")
        self.write(self._c(f"  {icon} [{kind}] {name}", "blue", "dim"))

    def ending(self, name: str) -> None:
        """结局横幅（按显示宽度自洽对齐）。"""
        content = f"★ 结局 · {name} ★"
        bar = "═" * (display_width(content) + 8)   # 内容两侧各 4 空格
        self.write()
        self.write(self._c(f"  ╔{bar}╗", "bright", "bold"))
        self.write(self._c(f"  ║    {content}    ║", "bright", "bold"))
        self.write(self._c(f"  ╚{bar}╝", "bright", "bold"))
        self.write()

    def history_view(self, entries: list) -> None:
        """回看：按顺序打印已发生的事件。"""
        self.write(self._c("  ── 历史回看 ──", "bold"))
        if not entries:
            self.write(self._c("  （暂无记录）", "dim"))
            return
        for e in entries:
            if e.kind == "line":
                self.write(f"    {self._c('[' + (e.scene or '') + ']', 'cyan', 'dim')}"
                           f" {self._c(e.speaker or '', 'yellow')}: {e.text}")
            elif e.kind == "narration":
                self.write(f"    {self._c('（旁白）' + (e.text or ''), 'magenta_b')}")
            elif e.kind == "choice":
                text = e.choice.get("text", "") if e.choice else ""
                self.write(f"    {self._c('→ 选择了：', 'green')}{text}")
            elif e.kind == "scene":
                self.write(f"    {self._c('◆ 场景 → ' + (e.scene or ''), 'cyan')}")
            elif e.kind == "fx":
                self.write(f"    {self._c('· ' + (e.text or ''), 'blue', 'dim')}")
            elif e.kind == "ending":
                self.write(f"    {self._c('★ ' + (e.text or ''), 'bright', 'bold')}")
        self.write(self._c("  ── 回看结束 ──", "bold"))

    def banner(self, title: str, subtitle: str = "") -> None:
        """开场标题。"""
        self.write(self._c(f"  ═══ {title} ═══", "bright", "bold"))
        if subtitle:
            self.write(self._c(f"    {subtitle}", "dim"))
        self.write()
