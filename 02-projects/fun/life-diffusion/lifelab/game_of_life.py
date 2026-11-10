"""康威生命游戏（Conway's Game of Life）B3/S23 规则引擎。

状态用「活细胞坐标集合」表示——对滑翔机、枪炮这类稀疏图案最省也最直观；
边界支持有限平面（默认）与环面（``wrap=True``，上下左右首尾相接）两种模式。
规则（二维 Moore 邻域，B3/S23）：恰好 3 个邻居出生，2 或 3 个邻居存活，
其余情况死亡（孤单 <2、拥挤 >3）。
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

LIVE_CHARS = frozenset("Oo*#")
DEAD_CHARS = frozenset(".- ")


class GameOfLife:
    """B3/S23 细胞自动机：一步进、批量演化、字符画互转。"""

    def __init__(self, width: int, height: int, cells: Iterable[tuple[int, int]] = (),
                 *, wrap: bool = False) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"网格尺寸必须为正，收到 {width}x{height}")
        self.width = int(width)
        self.height = int(height)
        self.wrap = bool(wrap)
        self.generation = 0
        self._live: set[tuple[int, int]] = set()
        self.add(cells)

    # ---------------------------------------------------------------- 构造
    @classmethod
    def from_text(cls, text: str, *, wrap: bool = False) -> "GameOfLife":
        """从 Gosper 风格字符画加载：``O``/``*``/``#`` 为活，``.``/``-``/空格为死。
        空行忽略、行首尾空白裁掉、短行按死亡补全（矩形取最宽行）。"""
        rows = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not rows:
            raise ValueError("图案文本为空")
        height = len(rows)
        width = max(len(r) for r in rows)
        cells: set[tuple[int, int]] = set()
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in LIVE_CHARS:
                    cells.add((x, y))
                elif ch not in DEAD_CHARS:
                    raise ValueError(f"未知字符 {ch!r}（行 {y}，列 {x}）")
        return cls(width, height, cells, wrap=wrap)

    # ---------------------------------------------------------------- 状态
    def add(self, cells: Iterable[tuple[int, int]]) -> None:
        """放入活细胞；越界直接报错，避免静默丢格子。"""
        for x, y in cells:
            x, y = int(x), int(y)
            if not (0 <= x < self.width and 0 <= y < self.height):
                raise ValueError(f"细胞 ({x},{y}) 超出 {self.width}x{self.height} 网格")
            self._live.add((x, y))

    @property
    def live_cells(self) -> frozenset[tuple[int, int]]:
        return frozenset(self._live)

    @property
    def population(self) -> int:
        return len(self._live)

    def __contains__(self, cell: object) -> bool:
        return cell in self._live

    def __len__(self) -> int:
        return len(self._live)

    def bbox(self) -> tuple[int, int, int, int] | None:
        """活细胞包围盒 ``(x0, y0, x1, y1)``；空网格返回 None。"""
        if not self._live:
            return None
        xs = [x for x, _ in self._live]
        ys = [y for _, y in self._live]
        return min(xs), min(ys), max(xs), max(ys)

    def copy(self) -> "GameOfLife":
        clone = GameOfLife(self.width, self.height, wrap=self.wrap)
        clone._live = set(self._live)
        clone.generation = self.generation
        return clone

    # ---------------------------------------------------------------- 演化
    def step(self) -> None:
        """原地演化一代（B3/S23）。"""
        live = self._live
        w, h, wrap = self.width, self.height, self.wrap
        counts: Counter[tuple[int, int]] = Counter()
        for x, y in live:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    nx, ny = x + dx, y + dy
                    if wrap:
                        nx %= w
                        ny %= h
                    elif not (0 <= nx < w and 0 <= ny < h):
                        continue
                    counts[(nx, ny)] += 1
        nxt: set[tuple[int, int]] = set()
        for cell, n in counts.items():
            if n == 3 or (n == 2 and cell in live):
                nxt.add(cell)
        self._live = nxt
        self.generation += 1

    def run(self, n: int) -> "GameOfLife":
        """批量原地演化 n 代，返回自身（便于链式调用）。"""
        if n < 0:
            raise ValueError("步数不能为负")
        for _ in range(n):
            self.step()
        return self

    def evolve(self, n: int) -> list["GameOfLife"]:
        """批量演化并收集每一代快照（含初始代，共 n+1 帧）。"""
        if n < 0:
            raise ValueError("步数不能为负")
        frames = [self.copy()]
        for _ in range(n):
            self.step()
            frames.append(self.copy())
        return frames

    # ---------------------------------------------------------------- 序列化
    def to_text(self, *, live: str = "O", dead: str = ".", trim: bool = True) -> str:
        """转回字符画；``trim=True`` 裁掉四周空行/列（图案平移到包围盒原点），
        需要绝对坐标逐格保持时用 ``trim=False``。"""
        if trim:
            box = self.bbox()
            if box is None:
                return ""
            x0, y0, x1, y1 = box
        else:
            x0, y0, x1, y1 = 0, 0, self.width - 1, self.height - 1
        lines = []
        for y in range(y0, y1 + 1):
            lines.append("".join(live if (x, y) in self._live else dead for x in range(x0, x1 + 1)))
        return "\n".join(lines)
