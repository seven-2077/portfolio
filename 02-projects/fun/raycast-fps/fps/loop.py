"""主循环：帧缓冲拼接整帧、HUD、限速与帧率统计、ANSI 无闪烁输出。

防闪烁的要点就一句话：**先在内存里拼好完整的一帧字符串，再一次
``stdout.write`` 到屏幕**，配合 ``\\x1b[H``（光标回家）覆盖上一帧 ——
逐行 print 会让终端一行行重绘，肉眼可见的抖动就是这么来的。
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from .combat import (check_end, check_exit, collect_pickups, damage_player,
                     try_shoot)
from .map import GameMap, load_map
from .player import KeyReader, Player, choose_start_angle, render_minimap
from .raycaster import render_walls
from .sprites import Enemy, Pickup, render_sprites, spawn_actors, update_enemies

__all__ = ["FrameBuffer", "Game", "ScriptedInput", "run", "enable_ansi"]

FIRE_COOLDOWN = 0.25      # 开火节奏（秒）：按住空格 = 约 4 枪/秒
MESSAGE_TTL = 3.0         # 提示存活时间


class FrameBuffer:
    """字符帧缓冲：宽 × 高的二维字符网格，最后 ``render()`` 拼成一个字符串。"""

    def __init__(self, width: int, height: int, fill: str = " "):
        self.width = width
        self.height = height
        self.cells = [[fill] * width for _ in range(height)]

    def clear(self, fill: str = " ") -> None:
        for row in self.cells:
            for x in range(self.width):
                row[x] = fill

    def put(self, x: int, y: int, ch: str) -> None:
        """写一个字符；越界直接忽略（裁剪，不抛异常）。"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y][x] = ch[0]

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y][x]
        return ""

    def write_text(self, x: int, y: int, text: str) -> None:
        for i, ch in enumerate(text):
            self.put(x + i, y, ch)

    def overlay_row(self, y: int, text: str) -> None:
        """整行覆盖（HUD 用），超宽截断。"""
        if not 0 <= y < self.height:
            return
        for x in range(self.width):
            self.cells[y][x] = text[x] if x < len(text) else " "

    def render(self) -> str:
        """一次拼接出整帧（无闪烁的关键）。"""
        return "\n".join("".join(row) for row in self.cells)


@dataclass
class ScriptedInput:
    """预录输入：脚本 [(动作集合, 持续帧数), ...] 按帧吐给主循环。"""

    script: List[Tuple[Set[str], int]]
    cursor: int = 0
    left: int = 0
    quit_when_done: bool = False      # 脚本走完是否自动发 quit

    def poll(self) -> Set[str]:
        if self.cursor >= len(self.script):
            return {"quit"} if self.quit_when_done else set()
        actions, frames = self.script[self.cursor]
        self.left += 1
        if self.left >= frames:
            self.cursor += 1
            self.left = 0
        return set(actions)


@dataclass
class Game:
    """一局游戏的全部状态 + 单帧的 step / draw。"""

    gmap: GameMap
    width: int = 80
    height: int = 24
    show_minimap: bool = True
    status: Optional[str] = None          # None / "win" / "lose"
    frames: int = 0
    fps: float = 0.0
    fire_cd: float = 0.0
    exit_taken: bool = False
    messages: List[Tuple[str, float]] = field(default_factory=list)
    visited: Set[Tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.player = Player(self.gmap.spawn[0], self.gmap.spawn[1])
        self.player.angle = choose_start_angle(self.gmap, self.player.x,
                                               self.player.y)
        self.enemies: List[Enemy]
        self.pickups: List[Pickup]
        self.enemies, self.pickups = spawn_actors(self.gmap)
        self.view_h = max(4, self.height - 2)     # 底部 2 行留给 HUD
        self.buf = FrameBuffer(self.width, self.height)

    # ---------- 状态小工具 ----------
    def push(self, text: str, ttl: float = MESSAGE_TTL) -> None:
        self.messages.append((text, ttl))
        del self.messages[:-4]                  # 只留最近几条

    @property
    def alive_enemies(self) -> int:
        return sum(1 for e in self.enemies if e.alive)

    # ---------- 一帧逻辑 ----------
    def step(self, actions: Set[str], dt: float) -> None:
        if dt <= 0:
            dt = 1e-6
        self.frames += 1
        self.messages = [(t, ttl - dt) for t, ttl in self.messages
                         if ttl - dt > 0]
        if "toggle_map" in actions:
            self.show_minimap = not self.show_minimap
        if self.status is not None:             # 胜负已分：世界冻结
            return
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.player.update(actions, dt, self.gmap)
        if "shoot" in actions and self.fire_cd <= 0.0:
            self.fire_cd = FIRE_COOLDOWN
            try_shoot(self)
        for event in update_enemies(self.enemies, self.gmap, self.player, dt):
            if event[0] == "attack":
                damage_player(self, event[1])
        for message in collect_pickups(self):
            self.push(message)
        message = check_exit(self)
        if message:
            self.push(message)
        self.visited.add((math.floor(self.player.x),
                          math.floor(self.player.y)))
        end = check_end(self)
        if end:
            self.status = end
            self.push("全部敌人已消灭，通关！" if end == "win"
                      else "血量归零——挑战失败")

    # ---------- 一帧画面 ----------
    def draw(self) -> str:
        buf = self.buf
        buf.clear()
        zbuf = render_walls(self.gmap, self.player, buf,
                            self.width, self.view_h)
        render_sprites(list(self.enemies) + list(self.pickups),
                       self.player, zbuf, buf, self.width, self.view_h)
        buf.put(self.width // 2, self.view_h // 2, "+")       # 准星
        if self.show_minimap:
            mini = render_minimap(self.gmap, self.player, self.enemies,
                                  self.pickups)
            for y, row in enumerate(mini):
                for x, ch in enumerate(row):
                    buf.put(x + 1, y + 1, ch)
        self._draw_hud(buf)
        return buf.render()

    def _draw_hud(self, buf: FrameBuffer) -> None:
        player = self.player
        filled = max(0, min(10, round(player.hp / 10)))
        gauge = "=" * filled + "-" * (10 - filled)
        hud = (f" HP[{gauge}]{player.hp:3d} AMMO {player.ammo:2d} "
               f"SCORE {player.score:05d} 敌 {self.alive_enemies}/"
               f"{len(self.enemies)} FPS {self.fps:4.1f} "
               f"{'地图 开' if self.show_minimap else '地图 关'}")
        buf.overlay_row(self.height - 2, hud)
        hint = "[WASD]移动 [←→/JL]转头 [空格]开火 [M]地图 [Q]退出"
        if self.status == "win":
            hint = f"*** 通关！得分 {player.score} —— [Q] 退出 ***"
        elif self.status == "lose":
            hint = f"*** 你死了 得分 {player.score} —— [Q] 退出 ***"
        elif self.messages:
            hint = f"{self.messages[-1][0]}   {hint}"
        buf.overlay_row(self.height - 1, hint)


# ---------------------------------------------------------------- 主循环
def enable_ansi() -> bool:
    """Windows 下打开 VT 转义序列，让 ``\\x1b[H`` 光标定位生效。"""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def run(game: Game, input_source=None, target_fps: float = 30.0,
        show: bool = True, realtime: bool = True,
        max_frames: Optional[int] = None,
        on_frame: Optional[Callable[[int, str], None]] = None,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep) -> Dict[str, float]:
    """跑主循环，返回统计（帧数 / 耗时 / 实测帧率）。"""
    source = input_source or KeyReader()
    ansi = False
    if show and sys.stdout.isatty():
        ansi = enable_ansi()
        if ansi:
            sys.stdout.write("\x1b[?25l\x1b[2J")
            sys.stdout.flush()
    dt = 1.0 / target_fps
    started = clock()
    last_tick = started
    frames = 0
    try:
        while True:
            actions = source.poll()
            if "quit" in actions:
                break
            frame_start = clock()
            game.step(actions, dt)
            frame = game.draw()
            if on_frame is not None:
                on_frame(frames, frame)
            frames += 1
            game.frames = frames
            tick = clock()
            period = tick - last_tick
            last_tick = tick
            if period > 1e-6:
                instant = 1.0 / period
                game.fps = instant if game.fps <= 0 else \
                    game.fps + (instant - game.fps) * 0.15
            if show:
                sys.stdout.write(("\x1b[H" + frame) if ansi
                                 else frame + "\n")
                sys.stdout.flush()
            if max_frames is not None and frames >= max_frames:
                break
            if realtime:
                remaining = dt - (clock() - frame_start)
                if remaining > 0:
                    sleep(remaining)
    finally:
        if ansi:
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()
    elapsed = clock() - started
    return {"frames": float(frames), "elapsed": elapsed,
            "fps": frames / elapsed if elapsed > 0 else 0.0}


def make_game(map_name: str = "crypt", seed: Optional[int] = None,
              width: int = 80, height: int = 24) -> Game:
    """按名字快速开局（含 random）。"""
    return Game(load_map(map_name, seed=seed), width=width, height=height)
