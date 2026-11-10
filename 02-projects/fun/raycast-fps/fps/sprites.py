"""精灵：敌人 / 拾取物的屏幕投影、画家算法排序、墙体遮挡与 AI。

投影用 Lodev 的相机矩阵逆变换：把「世界相对坐标」变到相机空间
``(横向偏移 tx, 纵向深度 ty)``，屏幕横坐标 = 半宽 × (1 + tx/ty) ——
和透视除法是同一件事，越远的物体既靠近画面中心也越小。

绘制顺序两条保险：

1. **画家算法** —— 先按距离从远到近排序，远的先画、近的后画（覆盖）；
2. **z-buffer 逐列遮挡** —— 每列记住墙的垂直距离，精灵深度更大就跳过，
   于是躲在墙后面的敌人即使排在后面也画不出来。
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .raycaster import shade_char

__all__ = ["Enemy", "Pickup", "SPRITE_ART", "ENEMY_SPEC",
           "spawn_actors", "update_enemies", "render_sprites",
           "sort_for_draw", "project_sprite", "SpriteProj", "bfs_path"]

CHAR_ASPECT = 0.5           # 终端字符高:宽 ≈ 2:1，横向要打对折才不胖
ATTACK_RANGE = 0.95         # 敌人近战距离
ATTACK_DAMAGE = 8
ATTACK_COOLDOWN = 1.1

# 字符图案：None = 透明，'0'-'9' = 该格亮度（和墙共用同一套明暗表）
SPRITE_ART: Dict[str, Tuple[Tuple[Optional[str], ...], ...]] = {
    "patrol": (
        (None, "9", "9", "9", None),
        (None, "9", "4", "9", None),
        ("7", "8", "8", "8", "7"),
        (None, "7", "7", "7", None),
        ("3", None, "6", None, "3"),
    ),
    "chaser": (
        ("8", None, "9", None, "8"),
        (None, "7", "8", "7", None),
        (None, "9", "3", "9", None),
        ("8", "9", "9", "9", "8"),
        (None, "7", "7", "7", None),
        ("4", None, "3", None, "4"),
    ),
    "ammo": (
        ("9", "9", "9"),
        ("9", "6", "9"),
        ("9", "9", "9"),
    ),
    "health": (
        (None, "9", None),
        ("9", "9", "9"),
        (None, "9", None),
    ),
}

ENEMY_SPEC: Dict[str, Dict[str, object]] = {
    "patrol": {"name": "哨兵", "hp": 50, "speed": 1.5, "sight": 10.0,
               "score": 100, "aggro_time": 4.0, "height_frac": 0.80,
               "radius": 0.30},
    "chaser": {"name": "猎杀者", "hp": 100, "speed": 2.6, "sight": 14.0,
               "score": 250, "aggro_time": 10.0, "height_frac": 0.85,
               "radius": 0.30},
}
PICKUP_VALUE = {"ammo": 12, "health": 30}
_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))


@dataclass
class Pickup:
    """拾取物：站在地板上，玩家走近即生效。"""

    x: float
    y: float
    kind: str = "ammo"
    taken: bool = False
    height_frac: float = 0.35

    @property
    def alive(self) -> bool:
        return not self.taken


@dataclass
class Enemy:
    """敌人：巡逻型沿格子转圈，追踪型用 BFS 找路咬人。"""

    x: float
    y: float
    kind: str = "patrol"
    hp: int = 0
    alive: bool = True
    aggro: float = 0.0          # 追击欲望剩余秒数（看见/被打中会刷新）
    cooldown: float = 0.0       # 攻击冷却
    dir_idx: int = 0            # 巡逻方向 0..3
    path: List[Tuple[int, int]] = field(default_factory=list)
    path_timer: float = 0.0
    path_target: Optional[Tuple[int, int]] = None

    def __post_init__(self) -> None:
        spec = ENEMY_SPEC[self.kind]
        if self.hp <= 0:
            self.hp = int(spec["hp"])       # type: ignore[arg-type]
        self.height_frac = float(spec["height_frac"])  # type: ignore[arg-type]
        self.radius = float(spec["radius"])  # type: ignore[arg-type]
        self.speed = float(spec["speed"])   # type: ignore[arg-type]

    # ---------- 状态 ----------
    @property
    def name(self) -> str:
        return str(ENEMY_SPEC[self.kind]["name"])

    @property
    def score_value(self) -> int:
        return int(ENEMY_SPEC[self.kind]["score"])  # type: ignore[arg-type]

    def hurt(self, amount: int) -> bool:
        """扣血，返回是否死亡；没死也记仇（aggro 拉满）。"""
        if not self.alive:
            return False
        self.hp = max(0, self.hp - amount)
        self.aggro = max(self.aggro, 999.0)
        if self.hp == 0:
            self.alive = False
            return True
        return False

    # ---------- AI ----------
    def update(self, gmap, player, dt: float) -> List[Tuple[str, int, "Enemy"]]:
        """一帧 AI：感知 → 追击或巡逻 → 近身攻击。返回事件列表。"""
        events: List[Tuple[str, int, "Enemy"]] = []
        if not self.alive:
            return events
        self.cooldown = max(0.0, self.cooldown - dt)
        dist = math.hypot(player.x - self.x, player.y - self.y)
        sight = float(ENEMY_SPEC[self.kind]["sight"])  # type: ignore[arg-type]
        los = dist <= sight and gmap.segment_clear(
            self.x, self.y, player.x, player.y)
        if los:
            self.aggro = float(ENEMY_SPEC[self.kind]["aggro_time"])  # type: ignore[arg-type]
        else:
            self.aggro = max(0.0, self.aggro - dt)
        if self.aggro > 0.0:
            self._chase(gmap, player.x, player.y, dt, los)
        else:
            self._patrol(gmap, dt)
        if player.alive and dist <= ATTACK_RANGE and self.cooldown <= 0.0:
            self.cooldown = ATTACK_COOLDOWN
            events.append(("attack", ATTACK_DAMAGE, self))
        return events

    def _step_toward(self, gmap, tx: float, ty: float, step: float) -> float:
        """朝目标走一步（撞墙的分量被吃掉 = 自然贴墙滑动），返回实际位移。"""
        dx, dy = tx - self.x, ty - self.y
        norm = math.hypot(dx, dy)
        if norm < 1e-9:
            return 0.0
        ox, oy = self.x, self.y
        self.x, self.y = gmap.try_move(self.x, self.y,
                                       dx / norm * step, dy / norm * step,
                                       self.radius)
        return math.hypot(self.x - ox, self.y - oy)

    def _patrol(self, gmap, dt: float) -> None:
        """巡逻：沿当前方向走，撞墙就顺时针换向（确定性，方便复盘）。"""
        step = self.speed * 0.7 * dt
        dx, dy = _DIRS[self.dir_idx]
        ox, oy = self.x, self.y
        self.x, self.y = gmap.try_move(self.x, self.y,
                                       dx * step, dy * step, self.radius)
        if math.hypot(self.x - ox, self.y - oy) < step * 0.5:
            self.dir_idx = (self.dir_idx + 1) % 4

    def _chase(self, gmap, px: float, py: float, dt: float,
               los: bool) -> None:
        """追击：看得见就直线扑上去；看不见 / 撞墙就 BFS 绕路。"""
        step = self.speed * dt
        if los and self._step_toward(gmap, px, py, step) >= step * 0.5:
            return
        self.path_timer -= dt
        target = (math.floor(px), math.floor(py))
        if (not self.path or self.path_timer <= 0.0
                or target != self.path_target):
            self.path = bfs_path(gmap, (math.floor(self.x), math.floor(self.y)),
                                 target)
            self.path_timer = 0.4
            self.path_target = target
        if not self.path:
            self._step_toward(gmap, px, py, step)
            return
        wx, wy = self.path[0][0] + 0.5, self.path[0][1] + 0.5
        if math.hypot(wx - self.x, wy - self.y) < 0.22:
            self.path.pop(0)
            if not self.path:
                return
            wx, wy = self.path[0][0] + 0.5, self.path[0][1] + 0.5
        self._step_toward(gmap, wx, wy, step)


def bfs_path(gmap, start: Tuple[int, int],
             goal: Tuple[int, int]) -> List[Tuple[int, int]]:
    """格子级 BFS：返回从 start 到 goal 的下一步序列（不含起点）。"""
    if start == goal or gmap.is_wall_cell(*goal):
        return []
    previous: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        if (cx, cy) == goal:
            break
        for dx, dy in _DIRS:
            nxt = (cx + dx, cy + dy)
            if nxt in previous or gmap.is_wall_cell(*nxt):
                continue
            previous[nxt] = (cx, cy)
            queue.append(nxt)
    if goal not in previous:
        return []
    path: List[Tuple[int, int]] = []
    cur: Optional[Tuple[int, int]] = goal
    while cur is not None and cur != start:
        path.append(cur)
        cur = previous[cur]
    path.reverse()
    return path


# ---------------------------------------------------------------- 投影与绘制
@dataclass
class SpriteProj:
    """精灵在屏幕上的落点（深度与 z-buffer 同为垂直距离口径）。"""

    depth: float
    screen_x: float
    top: float
    bottom: float
    width_px: float
    height_px: float


def project_sprite(actor, player, width: int,
                   view_h: int) -> Optional[SpriteProj]:
    """相机空间逆变换：世界偏移 → (tx 横向, ty 深度) → 屏幕矩形。"""
    art = SPRITE_ART.get(actor.kind)
    if art is None:
        return None
    rel_x, rel_y = actor.x - player.x, actor.y - player.y
    dir_x, dir_y = player.direction
    plane_x, plane_y = player.plane
    det = plane_x * dir_y - dir_x * plane_y
    if abs(det) < 1e-9:
        return None
    inv = 1.0 / det
    tx = inv * (dir_y * rel_x - dir_x * rel_y)
    ty = inv * (-plane_y * rel_x + plane_x * rel_y)
    if ty <= 0.05:                      # 在身后或贴着脸，跳过
        return None
    screen_x = (width * 0.5) * (1.0 + tx / ty)
    wall_h = view_h / ty
    height_px = wall_h * actor.height_frac
    rows_n, cols_n = len(art), len(art[0])
    width_px = height_px * (cols_n / rows_n) * CHAR_ASPECT
    bottom = view_h * 0.5 + wall_h * 0.5     # 站在地板上 = 墙的下沿
    return SpriteProj(ty, screen_x, bottom - height_px, bottom,
                      width_px, height_px)


def sort_for_draw(actors: Iterable, player) -> List:
    """画家算法：距离玩家越远越先画（近的后画、盖在上面）。"""
    return sorted((a for a in actors if a.alive),
                  key=lambda a: -((a.x - player.x) ** 2
                                  + (a.y - player.y) ** 2))


def render_sprites(actors: Iterable, player, zbuf: Sequence[float], buf,
                   width: int, view_h: int) -> None:
    """把存活精灵画进帧缓冲：远近排序 + 逐列 z-buffer 遮挡裁剪。"""
    for actor in sort_for_draw(actors, player):
        proj = project_sprite(actor, player, width, view_h)
        if proj is None or proj.width_px <= 0 or proj.height_px <= 0:
            continue
        art = SPRITE_ART[actor.kind]
        rows_n, cols_n = len(art), len(art[0])
        left = proj.screen_x - proj.width_px * 0.5
        for xi in range(max(0, math.floor(left)),
                        min(width, math.ceil(left + proj.width_px))):
            if proj.depth > zbuf[xi] + 1e-9:        # 墙在前面 → 被挡住
                continue
            sx = int((xi + 0.5 - left) / proj.width_px * cols_n)
            if not 0 <= sx < cols_n:
                continue
            for yi in range(max(0, math.floor(proj.top)),
                            min(view_h, math.ceil(proj.bottom))):
                sy = int((yi + 0.5 - proj.top) / proj.height_px * rows_n)
                if not 0 <= sy < rows_n:
                    continue
                cell = art[sy][sx]
                if cell is None:
                    continue
                buf.put(xi, yi, shade_char(proj.depth, 0, int(cell)))


# ---------------------------------------------------------------- 实体管理
def spawn_actors(gmap) -> Tuple[List[Enemy], List[Pickup]]:
    """按地图出生点清单生成敌人与拾取物。"""
    enemies = [Enemy(x, y, kind) for x, y, kind in gmap.enemy_spawns]
    pickups = [Pickup(x, y, kind) for x, y, kind in gmap.pickup_spawns]
    return enemies, pickups


def update_enemies(enemies: Iterable, gmap, player,
                   dt: float) -> List[Tuple[str, int, Enemy]]:
    """驱动全部敌人一帧 AI，汇总事件（如 "attack" 近战命中）。"""
    events: List[Tuple[str, int, Enemy]] = []
    for enemy in enemies:
        events.extend(enemy.update(gmap, player, dt))
    return events
