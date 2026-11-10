"""玩家：移动与转向、msvcrt 非阻塞读键、小地图渲染。

按键协议分两层，方便测试::

    KeyReader.poll()   从终端抓一帧按键 → 动作名集合（"forward" 等）
    keys_to_actions()  纯函数：按键序列 → 动作集合（单测直接喂字符）

图例：W/S 前进后退、A/D 平移、← → 或 J/L 转头、空格开火、M 小地图、Q 退出。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Set, Tuple

from .map import GameMap
from .raycaster import cast_ray

__all__ = ["Player", "KeyReader", "keys_to_actions", "render_minimap",
           "choose_start_angle", "MOVE_SPEED", "TURN_SPEED", "PLAYER_RADIUS"]

MOVE_SPEED = 3.2        # 格 / 秒
TURN_SPEED = 2.6        # 弧度 / 秒
PLAYER_RADIUS = 0.22    # 碰撞圆半径

KEY_ACTIONS = {
    "w": "forward", "s": "back", "a": "strafe_l", "d": "strafe_r",
    "j": "turn_l", "l": "turn_r",
    " ": "shoot", "f": "shoot", "m": "toggle_map",
    "q": "quit", "\x1b": "quit", "\x03": "quit",
}
ARROW_ACTIONS = {"H": "forward", "P": "back", "K": "turn_l", "M": "turn_r"}


def keys_to_actions(keys: Sequence[str]) -> Set[str]:
    """按键字符序列 → 动作集合；方向键是 ``\\x00``/``\\xe0`` 前缀 + 码字节。"""
    actions: Set[str] = set()
    i = 0
    while i < len(keys):
        ch = keys[i]
        i += 1
        if ch in ("\x00", "\xe0"):
            if i < len(keys):
                action = ARROW_ACTIONS.get(keys[i])
                i += 1
                if action:
                    actions.add(action)
            continue
        action = KEY_ACTIONS.get(ch)
        if action:
            actions.add(action)
    return actions


def _msvcrt_read_char() -> Optional[str]:
    """Windows 非阻塞读一个字符；无按键或平台不支持时返回 None。"""
    try:
        import msvcrt
    except ImportError:
        return None
    if msvcrt.kbhit():
        return msvcrt.getwch()
    return None


class KeyReader:
    """把终端缓冲里的按键翻译成动作集（每帧调用一次 ``poll``）。"""

    def __init__(self, read_char: Optional[Callable[[], Optional[str]]] = None):
        self._read = read_char or _msvcrt_read_char

    def poll(self, max_keys: int = 24) -> Set[str]:
        keys: List[str] = []
        for _ in range(max_keys):
            ch = self._read()
            if ch is None:
                break
            keys.append(ch)
        return keys_to_actions(keys)


def choose_start_angle(gmap: GameMap, x: float, y: float) -> float:
    """开局朝向：环视一圈，选视野最开阔的方向（免得开局怼着墙看）。"""
    best_angle, best_dist = 0.0, -1.0
    for i in range(16):
        angle = i * math.tau / 16
        dist = cast_ray(gmap, x, y, angle).dist
        if dist > best_dist:
            best_angle, best_dist = angle, dist
    return best_angle


@dataclass
class Player:
    """玩家状态：位置、朝向、血量弹药得分。"""

    x: float
    y: float
    angle: float = 0.0
    hp: int = 100
    ammo: int = 24
    score: int = 0
    alive: bool = True
    radius: float = PLAYER_RADIUS
    fov: float = math.radians(66.0)

    @property
    def direction(self) -> Tuple[float, float]:
        return math.cos(self.angle), math.sin(self.angle)

    @property
    def plane(self) -> Tuple[float, float]:
        """相机平面：垂直于视线，长度 = tan(fov/2)，决定视野宽度。"""
        half = math.tan(self.fov * 0.5)
        dx, dy = self.direction
        return -dy * half, dx * half

    def take_damage(self, amount: int) -> None:
        if not self.alive:
            return
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.alive = False

    def update(self, actions: Set[str], dt: float, gmap: GameMap) -> None:
        """一帧的移动：先转头，再把「前后 + 平移」合成向量去撞圆检测。"""
        if "turn_l" in actions:
            self.angle -= TURN_SPEED * dt
        if "turn_r" in actions:
            self.angle += TURN_SPEED * dt
        self.angle = (self.angle + math.pi) % math.tau - math.pi
        dir_x, dir_y = self.direction
        side_x, side_y = -dir_y, dir_x
        vx = vy = 0.0
        if "forward" in actions:
            vx += dir_x
            vy += dir_y
        if "back" in actions:
            vx -= dir_x
            vy -= dir_y
        if "strafe_l" in actions:
            vx -= side_x
            vy -= side_y
        if "strafe_r" in actions:
            vx += side_x
            vy += side_y
        if vx or vy:
            norm = math.hypot(vx, vy)
            step = MOVE_SPEED * dt / norm
            self.x, self.y = gmap.try_move(self.x, self.y,
                                           vx * step, vy * step, self.radius)


def render_minimap(gmap: GameMap, player: Player,
                   enemies: Iterable = (),
                   pickups: Iterable = (),
                   width: int = 17, height: int = 9) -> List[str]:
    """玩家周围的小地图窗口：# 墙、E 出口、X 敌人、+ 拾取、@ 玩家。"""
    px, py = math.floor(player.x), math.floor(player.y)
    left, top = px - width // 2, py - height // 2
    canvas = []
    for row in range(height):
        line = []
        for col in range(width):
            cx, cy = left + col, top + row
            if not gmap.in_bounds(cx, cy):
                line.append("#")
            elif gmap.is_wall_cell(cx, cy):
                line.append("#")
            elif gmap.is_exit(cx + 0.5, cy + 0.5):
                line.append("E")
            else:
                line.append(".")
        canvas.append(line)
    for entity in list(pickups) + list(enemies):
        if hasattr(entity, "alive") and not entity.alive:
            continue
        ex, ey = math.floor(entity.x) - left, math.floor(entity.y) - top
        if 0 <= ex < width and 0 <= ey < height:
            canvas[ey][ex] = "X" if hasattr(entity, "hp") else "+"
    mx, my = px - left, py - top
    if 0 <= mx < width and 0 <= my < height:
        canvas[my][mx] = "@"
    return ["".join(row) for row in canvas]
