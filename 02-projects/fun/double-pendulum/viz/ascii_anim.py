"""终端 ASCII 实时动画：摆杆与摆球字符画，msvcrt 非阻塞退出。

两种模式：
    interactive = True   全屏实时动画（清屏 + 按帧 sleep），msvcrt 非阻塞
                         轮询 q / Esc / Ctrl+C 随时退出；
    interactive = False  固定帧数的演示模式：不清屏不 sleep，只抽样打印
                         首/中/末帧 —— 适合管道输出、测试与 demo 录制。

字符画约定：'+' 支点 · '.' 摆杆 · 'O' 摆球 · ':' 端点残影。
"""

from __future__ import annotations

import math
import os
import sys
import time
from math import cos, sin
from typing import Callable, Sequence, TextIO

from pendulum import energy as _energy
from pendulum.integrate import RK4
from pendulum.ode import DEFAULT, Params

try:  # Windows 专用：非阻塞键盘轮询
    import msvcrt
except ImportError:  # 非 Windows 平台降级：无退出轮询
    msvcrt = None  # type: ignore[assignment]

__all__ = ["render", "format_frame", "run_animation", "DEFAULT_STATE"]

WIDTH = 61
HEIGHT = 31

CHAR_PIVOT = "+"
CHAR_ROD = "."
CHAR_BOB = "O"
CHAR_TRAIL = ":"

# 演示默认初值：θ1 = 170°, θ2 = -120°，静止释放 —— 立即进入混沌摆动
DEFAULT_STATE: tuple[float, float, float, float] = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)


def _cell(x: float, y: float, width: int, height: int, r: float = 2.0) -> tuple[int, int]:
    """世界坐标 → 字符网格 (row, col)，按总杆长 r 自适应视野。

    视野取对称方框 x ∈ [-1.15r, 1.15r]、y ∈ [-1.2r, 1.2r]：
    上界覆盖「倒立」姿态（两杆朝上时 y 可达 +2r），下界覆盖完全下垂。
    """
    wx = 1.15 * r
    wx0, wx1 = -wx, wx
    wy0, wy1 = -1.2 * r, 1.2 * r
    col = round((x - wx0) / (wx1 - wx0) * (width - 1))
    row = round((wy1 - y) / (wy1 - wy0) * (height - 1))
    return (max(0, min(height - 1, row)), max(0, min(width - 1, col)))


def render(
    state: Sequence[float],
    params: Params = DEFAULT,
    width: int = WIDTH,
    height: int = HEIGHT,
    trail: Sequence[tuple[float, float]] = (),
) -> list[str]:
    """把当前状态画成字符网格（纯函数，便于测试）。"""
    th1, _w1, th2, _w2 = state
    l1, l2 = params.l1, params.l2
    r = l1 + l2

    grid = [[" "] * width for _ in range(height)]

    def put(row: int, col: int, ch: str) -> None:
        grid[row][col] = ch

    # 1) 端点残影
    for (x, y) in trail:
        row, col = _cell(x, y, width, height, r)
        put(row, col, CHAR_TRAIL)

    # 2) 两段摆杆（沿线采样）
    x1, y1 = l1 * sin(th1), -l1 * cos(th1)
    x2, y2 = x1 + l2 * sin(th2), y1 - l2 * cos(th2)
    for (ax, ay, bx, by, n) in ((0.0, 0.0, x1, y1, 18), (x1, y1, x2, y2, 18)):
        for k in range(n + 1):
            f = k / n
            row, col = _cell(ax + (bx - ax) * f, ay + (by - ay) * f, width, height, r)
            if grid[row][col] == " ":
                put(row, col, CHAR_ROD)

    # 3) 支点与摆球（后画，保证不被杆覆盖）
    row, col = _cell(0.0, 0.0, width, height, r)
    put(row, col, CHAR_PIVOT)
    for (x, y) in ((x1, y1), (x2, y2)):
        row, col = _cell(x, y, width, height, r)
        put(row, col, CHAR_BOB)

    return ["".join(row) for row in grid]


def format_frame(rows: Sequence[str], header: str = "", footer: str = "") -> str:
    """网格 + 标题行（能量/时间 HUD）拼成一帧文本。"""
    lines = []
    if header:
        lines.append(header)
    border = "+" + "-" * len(rows[0]) + "+"
    lines.append(border)
    lines.extend(f"|{row}|" for row in rows)
    lines.append(border)
    if footer:
        lines.append(footer)
    return "\n".join(lines) + "\n"


def _poll_quit() -> bool:
    """msvcrt 非阻塞轮询：有 q / Q / Esc 按下即返回 True（顺带排空按键队列）。"""
    if msvcrt is None:
        return False
    while msvcrt.kbhit():
        ch = msvcrt.getwch()
        if ch in ("\x1b", "q", "Q"):
            return True
    return False


def _clear(out: TextIO) -> None:
    if os.name == "nt":
        os.system("cls")  # 兼容旧 conhost；帧内容仍写入 out
    else:
        out.write("\x1b[2J\x1b[H")


def run_animation(
    state0: Sequence[float] | None = None,
    *,
    frames: int = 90,
    dt: float = 1.0 / 30.0,
    params: Params = DEFAULT,
    width: int = WIDTH,
    height: int = HEIGHT,
    sleep_s: float = 1.0 / 30.0,
    interactive: bool | None = None,
    trail_len: int = 30,
    quit_poll: Callable[[], bool] | None = None,
    out: TextIO | None = None,
) -> int:
    """跑固定帧数的摆动画，返回实际渲染的帧数。

    interactive=None 时自动检测 stdout 是否为 TTY：是 → 全屏实时动画；
    否 → 演示模式（抽样打印首/中/末帧，不 sleep、不清屏）。
    quit_poll 可注入自定义退出条件（测试用），默认走 msvcrt 轮询。
    """
    out = sys.stdout if out is None else out
    if interactive is None:
        interactive = getattr(out, "isatty", lambda: False)()

    state = tuple(DEFAULT_STATE if state0 is None else state0)
    rk = RK4(params=params, dt=dt)
    # 帧间隔（1/30 s）对 RK4 太粗 → 内部用 ≤2ms 子步推进，HUD 能量才不虚跳
    sub = max(1, math.ceil(dt / 0.002))
    h = dt / sub
    trail: list[tuple[float, float]] = []
    shown = 0
    sample_idx = {0, frames // 2, frames - 1}

    try:
        for i in range(frames):
            t = i * dt
            header = (f" 双摆混沌  t = {t:5.2f}s  E = {_energy.total(state, params):8.4f} J"
                      + ("   [q/Esc 退出]" if interactive else "   演示模式"))
            if interactive or i in sample_idx:
                rows = render(state, params, width, height, trail=trail[-trail_len:])
                if interactive:
                    _clear(out)
                else:
                    out.write(f"--- frame {i + 1}/{frames} ---\n")
                out.write(format_frame(rows, header=header))
                out.flush()
                shown += 1

            # 残影：记下摆球 2 端点
            x1 = params.l1 * sin(state[0])
            y1 = -params.l1 * cos(state[0])
            trail.append((x1 + params.l2 * sin(state[2]), y1 - params.l2 * cos(state[2])))

            if quit_poll is not None:
                if quit_poll():
                    break
            elif interactive and _poll_quit():
                break

            if interactive and sleep_s > 0:
                time.sleep(sleep_s)
            for k in range(sub):
                state = rk.step(state, t + k * h, h)
    except KeyboardInterrupt:
        pass  # Ctrl+C 优雅收场

    return shown
