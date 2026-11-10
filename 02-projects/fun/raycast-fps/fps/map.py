"""网格地图：图例解析与校验、圆-网格碰撞、视线检测、随机迷宫生成。

一张地图就是一组等宽字符行，图例::

    # 1 2 3   墙（1 砖 / 2 石 / 3 金属板；# 是 1 的别名）
    .         地板
    P         玩家出生点（有且只有一个）
    E         出口（有且只有一个）
    t c       敌人：t 巡逻型、c 追踪型
    a h       拾取物：a 弹药、h 医疗

``from_rows`` 跑完整校验：图例合法、边框封闭、出生点与出口唯一、
所有实体从出生点连通可达；任何一条不满足都抛 :class:`MapError`。
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

__all__ = ["MapError", "GameMap", "MAPS", "load_map",
           "generate_random_map", "flood_reach"]

WALL_OF = {"#": 1, "1": 1, "2": 2, "3": 3}
ENTITY_OF = {"t": ("enemy", "patrol"), "c": ("enemy", "chaser"),
             "a": ("pickup", "ammo"), "h": ("pickup", "health")}
LEGEND = set(WALL_OF) | set(ENTITY_OF) | {".", "P", "E"}

_N8 = ((1, 0), (-1, 0), (0, 1), (0, -1))


class MapError(ValueError):
    """地图不合法时抛出，信息直接给玩家看。"""


def flood_reach(grid: Sequence[Sequence[int]],
                start: Tuple[int, int]) -> Set[Tuple[int, int]]:
    """从 ``start`` 出发能走到的所有地板格（BFS），用于连通性校验。"""
    h, w = len(grid), len(grid[0])
    seen = {start}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in _N8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen \
                    and grid[ny][nx] == 0:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


@dataclass
class GameMap:
    """解析完成的地图：网格、出生点、出口、实体清单。"""

    name: str
    rows: Tuple[str, ...]
    grid: List[List[int]]
    spawn: Tuple[float, float]
    exit_cell: Tuple[int, int]
    enemy_spawns: List[Tuple[float, float, str]] = field(default_factory=list)
    pickup_spawns: List[Tuple[float, float, str]] = field(default_factory=list)

    # ---------- 查询 ----------
    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def exit_pos(self) -> Tuple[float, float]:
        return self.exit_cell[0] + 0.5, self.exit_cell[1] + 0.5

    def in_bounds(self, cx: int, cy: int) -> bool:
        return 0 <= cx < self.width and 0 <= cy < self.height

    def cell(self, cx: int, cy: int) -> int:
        """格值：0=地板，1..3=墙材质；越界按墙处理（值 1）。"""
        if not self.in_bounds(cx, cy):
            return 1
        return self.grid[cy][cx]

    def is_wall_cell(self, cx: int, cy: int) -> bool:
        return self.cell(cx, cy) != 0

    def is_wall_at(self, fx: float, fy: float) -> bool:
        return self.is_wall_cell(math.floor(fx), math.floor(fy))

    def is_exit(self, fx: float, fy: float) -> bool:
        return (math.floor(fx), math.floor(fy)) == self.exit_cell

    def floor_cells(self) -> List[Tuple[int, int]]:
        return [(x, y) for y in range(self.height) for x in range(self.width)
                if self.grid[y][x] == 0]

    # ---------- 碰撞（圆 vs 网格 AABB）----------
    def circle_hits_wall(self, x: float, y: float, r: float) -> bool:
        """半径 ``r`` 的圆心在 (x, y) 时是否压到墙。"""
        for cy in range(math.floor(y - r), math.floor(y + r) + 1):
            for cx in range(math.floor(x - r), math.floor(x + r) + 1):
                if not self.is_wall_cell(cx, cy):
                    continue
                px = min(max(x, cx), cx + 1.0)
                py = min(max(y, cy), cy + 1.0)
                if (x - px) ** 2 + (y - py) ** 2 < r * r - 1e-12:
                    return True
        return False

    def try_move(self, x: float, y: float, dx: float, dy: float,
                 r: float) -> Tuple[float, float]:
        """按 x、y 分轴尝试位移：撞墙的轴被吃掉，另一轴保留 = 贴墙滑动。"""
        nx = x + dx
        if self.circle_hits_wall(nx, y, r):
            nx = x
        ny = y + dy
        if self.circle_hits_wall(nx, ny, r):
            ny = y
        return nx, ny

    # ---------- 视线（线段穿越网格的 DDA）----------
    def segment_clear(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        """两点间是否无墙遮挡（Amanatides & Woo 逐格行走）。"""
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return not self.is_wall_at(x0, y0)
        cx, cy = math.floor(x0), math.floor(y0)
        ex, ey = math.floor(x1), math.floor(y1)
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        t_dx = abs(1.0 / dx) if dx else math.inf
        t_dy = abs(1.0 / dy) if dy else math.inf
        t_max_x = (((cx + 1) if dx > 0 else cx) - x0) / dx if dx else math.inf
        t_max_y = (((cy + 1) if dy > 0 else cy) - y0) / dy if dy else math.inf
        for _ in range(self.width * self.height + 8):
            if self.is_wall_cell(cx, cy):
                return False
            if (cx, cy) == (ex, ey):
                return True
            if t_max_x < t_max_y:
                cx += step_x
                t_max_x += t_dx
            else:
                cy += step_y
                t_max_y += t_dy
        return False

    # ---------- 解析 ----------
    @classmethod
    def from_rows(cls, rows: Sequence[str], name: str = "map") -> "GameMap":
        validate_rows(rows)
        grid: List[List[int]] = []
        enemy_spawns: List[Tuple[float, float, str]] = []
        pickup_spawns: List[Tuple[float, float, str]] = []
        spawn: Optional[Tuple[float, float]] = None
        exit_cell: Optional[Tuple[int, int]] = None
        for y, row in enumerate(rows):
            line: List[int] = []
            for x, ch in enumerate(row):
                if ch in WALL_OF:
                    line.append(WALL_OF[ch])
                else:
                    line.append(0)
                    if ch == "P":
                        spawn = (x + 0.5, y + 0.5)
                    elif ch == "E":
                        exit_cell = (x, y)
                    elif ch in ENTITY_OF:
                        kind_group, kind = ENTITY_OF[ch]
                        pos = (x + 0.5, y + 0.5)
                        if kind_group == "enemy":
                            enemy_spawns.append((*pos, kind))
                        else:
                            pickup_spawns.append((*pos, kind))
            grid.append(line)
        assert spawn is not None and exit_cell is not None  # validate_rows 已保证
        _check_connected(grid, spawn, exit_cell, enemy_spawns, pickup_spawns)
        return cls(name=name, rows=tuple(rows), grid=grid, spawn=spawn,
                   exit_cell=exit_cell, enemy_spawns=enemy_spawns,
                   pickup_spawns=pickup_spawns)


def validate_rows(rows: Sequence[str]) -> None:
    """图例 / 尺寸 / 边框 / 出生点与出口唯一性的静态校验（不含连通性）。"""
    if not rows:
        raise MapError("地图不能为空")
    width = len(rows[0])
    if width < 5 or len(rows) < 5:
        raise MapError("地图太小（至少 5×5）")
    for i, row in enumerate(rows):
        if len(row) != width:
            raise MapError(f"第 {i} 行宽 {len(row)}，应为 {width}")
        bad = set(row) - LEGEND
        if bad:
            raise MapError(f"第 {i} 行含非法字符 {sorted(bad)}")
    for x in range(width):
        if rows[0][x] not in WALL_OF or rows[-1][x] not in WALL_OF:
            raise MapError("上下边框必须全是墙")
    for row in rows:
        if row[0] not in WALL_OF or row[-1] not in WALL_OF:
            raise MapError("左右边框必须全是墙")
    total = "".join(rows)
    if total.count("P") != 1:
        raise MapError(f"出生点 P 必须恰好一个（实际 {total.count('P')}）")
    if total.count("E") != 1:
        raise MapError(f"出口 E 必须恰好一个（实际 {total.count('E')}）")


def _check_connected(grid: List[List[int]], spawn: Tuple[float, float],
                     exit_cell: Tuple[int, int],
                     enemies: List[Tuple[float, float, str]],
                     pickups: List[Tuple[float, float, str]]) -> None:
    start = (math.floor(spawn[0]), math.floor(spawn[1]))
    reach = flood_reach(grid, start)
    if exit_cell not in reach:
        raise MapError("出口与出生点不连通")
    for x, y, _ in enemies + pickups:
        if (math.floor(x), math.floor(y)) not in reach:
            raise MapError(f"实体 ({math.floor(x)},{math.floor(y)}) 无法从出生点到达")


# ---------------------------------------------------------------- 手工地图
CRYPT_ROWS = [
    "################",
    "#P...#.....a..E#",
    "#.11.#.1111.#..#",
    "#.#..#.#...#.#.#",
    "#.#.11.#.1.#.#.#",
    "#...#..#...#.#.#",
    "#11.#..#.111.#.#",
    "#...#..#.....#.#",
    "#.111..##.##.#.#",
    "#......#t..#.#.#",
    "#.####.#.c.#.#.#",
    "#a....h#...#.t.#",
    "#......#...#...#",
    "#..222333...#..#",
    "################",
]

VAULT_ROWS = [
    "##################",
    "#P...2......a...E#",
    "#.22.2.2222.222..#",
    "#.#..#.....#....c#",
    "#.#.22.222.#.22..#",
    "#...#..2#2.#.#...#",
    "#22.#..#.#.#.#.22#",
    "#...#..#.#...#...#",
    "#.222..#.#####.#.#",
    "#.....2#...t...#.#",
    "#.#####..22222.#.#",
    "#a..t..#....c..#.#",
    "#..h...2..t....#.#",
    "#....a.2......3..#",
    "##################",
]

MAPS: Dict[str, GameMap] = {
    "crypt": GameMap.from_rows(CRYPT_ROWS, "crypt"),
    "vault": GameMap.from_rows(VAULT_ROWS, "vault"),
}


def load_map(name: str, seed: Optional[int] = None) -> GameMap:
    """按名字取手工地图，或 ``name="random"`` 现场生成一张。"""
    if name in MAPS:
        return MAPS[name]
    if name == "random":
        return generate_random_map(seed=seed)
    raise KeyError(f"未知地图 {name!r}，可选：{sorted(MAPS)} / random")


# ---------------------------------------------------------------- 随机生成
def generate_random_map(width: int = 15, height: int = 15,
                        seed: Optional[int] = None, enemies: int = 4,
                        pickups: int = 3, name: str = "random") -> GameMap:
    """随机迷宫：递归回溯挖洞 → 少量开口做环 → 铺材质、放出生点/出口/实体。

    生成结果一律再走 ``from_rows`` 完整校验，保证和手工地图同规格。
    """
    rng = random.Random(seed)
    w = width + 1 if width % 2 == 0 else width
    h = height + 1 if height % 2 == 0 else height
    w, h = max(w, 9), max(h, 9)
    grid = [[1] * w for _ in range(h)]

    # 递归回溯挖洞（步长 2 保证走廊规整）
    stack = [(1, 1)]
    grid[1][1] = 0
    while stack:
        cx, cy = stack[-1]
        options = [(cx + 2 * dx, cy + 2 * dy) for dx, dy in _N8
                   if 1 <= cx + 2 * dx < w - 1 and 1 <= cy + 2 * dy < h - 1
                   and grid[cy + 2 * dy][cx + 2 * dx] == 1]
        if not options:
            stack.pop()
            continue
        nx, ny = rng.choice(options)
        grid[(cy + ny) // 2][(cx + nx) // 2] = 0
        grid[ny][nx] = 0
        stack.append((nx, ny))

    # 打通几堵隔墙，让迷宫有环路（死胡同太多会走得很憋屈）
    loops = max(2, (w * h) // 45)
    candidates = [(x, y) for y in range(2, h - 2) for x in range(2, w - 2)
                  if grid[y][x] == 1
                  and ((grid[y][x - 1] == 0 and grid[y][x + 1] == 0)
                       or (grid[y - 1][x] == 0 and grid[y + 1][x] == 0))]
    for x, y in rng.sample(candidates, min(loops, len(candidates))):
        grid[y][x] = 0

    # 墙体材质：砖为主，石与金属板点缀
    for y in range(h):
        for x in range(w):
            if grid[y][x] == 1:
                grid[y][x] = rng.choices((1, 2, 3), weights=(6, 3, 2))[0]

    # 出生点在左上角，出口取离它最远的地板格
    spawn_cell = (1, 1)
    dist = _bfs_dist(grid, spawn_cell)
    exit_cell = max(dist, key=lambda c: dist[c])
    floor_pool = sorted(c for c in dist if c != spawn_cell and c != exit_cell)

    def pick(min_dist: int, taken: Set[Tuple[int, int]]):
        pool = [c for c in floor_pool
                if dist[c] >= min_dist and c not in taken]
        if not pool:
            return None
        cell = rng.choice(pool)
        taken.add(cell)
        return cell

    taken: Set[Tuple[int, int]] = {spawn_cell, exit_cell}
    enemy_cells = []
    for _ in range(enemies):
        cell = pick(4, taken)
        if cell:
            enemy_cells.append((*cell, rng.choice(("patrol", "chaser"))))
    pickup_cells = []
    for _ in range(pickups):
        cell = pick(2, taken)
        if cell:
            pickup_cells.append((*cell, rng.choice(("ammo", "health"))))

    entity_at = {}
    for ex, ey, kind in enemy_cells:
        entity_at[(ex, ey)] = "t" if kind == "patrol" else "c"
    for px, py, kind in pickup_cells:
        entity_at[(px, py)] = "a" if kind == "ammo" else "h"

    rows = []
    for y in range(h):
        line = []
        for x in range(w):
            if (x, y) == spawn_cell:
                line.append("P")
            elif (x, y) == exit_cell:
                line.append("E")
            elif (x, y) in entity_at:
                line.append(entity_at[(x, y)])
            elif grid[y][x] == 0:
                line.append(".")
            else:
                line.append(str(grid[y][x]))
        rows.append("".join(line))
    return GameMap.from_rows(rows, name=name)


def _bfs_dist(grid: Sequence[Sequence[int]],
              start: Tuple[int, int]) -> Dict[Tuple[int, int], int]:
    """从 start 到各地板格的步数（出口/实体选址用）。"""
    dist: Dict[Tuple[int, int], int] = {start: 0}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in _N8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < len(grid[0]) and 0 <= ny < len(grid) \
                    and (nx, ny) not in dist and grid[ny][nx] == 0:
                dist[(nx, ny)] = dist[(cx, cy)] + 1
                queue.append((nx, ny))
    return dist
