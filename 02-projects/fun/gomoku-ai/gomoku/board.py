"""15x15 棋盘状态：落子、提子（悔棋）、候选走法生成。

棋盘用二维列表表示，0 为空点，1 为黑子，2 为白子。
候选走法 = 已有棋子的邻域（切比雪夫距离 <= radius 的空点），
这样搜索树只在"有事发生"的地方展开，而不是 225 个空点全枚举。
"""

from __future__ import annotations

SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2
PLAYERS = (BLACK, WHITE)


def opponent(player: int) -> int:
    """返回对手方。"""
    return WHITE if player == BLACK else BLACK


class Board:
    """五子棋棋盘：只依赖标准库，支持落子、提子与克隆。"""

    def __init__(self, size: int = SIZE) -> None:
        self.size = size
        self.grid: list[list[int]] = [[EMPTY] * size for _ in range(size)]
        # 历史栈：(x, y, player)，悔棋时按后进先出恢复
        self.history: list[tuple[int, int, int]] = []

    # ---------- 基本访问 ----------

    def get(self, x: int, y: int) -> int:
        return self.grid[y][x]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    @property
    def last_move(self) -> tuple[int, int] | None:
        if not self.history:
            return None
        x, y, _ = self.history[-1]
        return (x, y)

    def is_full(self) -> bool:
        return len(self.history) >= self.size * self.size

    def empties(self) -> list[tuple[int, int]]:
        """全部空点（按行扫描顺序，保证确定性）。"""
        out = []
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] == EMPTY:
                    out.append((x, y))
        return out

    # ---------- 落子 / 提子 ----------

    def play(self, x: int, y: int, player: int) -> bool:
        """落子。非法（越界 / 占位 / 非法棋手）返回 False，不改状态。"""
        if player not in PLAYERS or not self.in_bounds(x, y):
            return False
        if self.grid[y][x] != EMPTY:
            return False
        self.grid[y][x] = player
        self.history.append((x, y, player))
        return True

    def undo(self) -> tuple[int, int, int] | None:
        """提子（悔棋一步）。历史为空返回 None。"""
        if not self.history:
            return None
        x, y, player = self.history.pop()
        self.grid[y][x] = EMPTY
        return (x, y, player)

    # ---------- 走法生成 ----------

    def neighbors(self, x: int, y: int, radius: int = 1) -> list[tuple[int, int]]:
        """(x, y) 周围半径 radius 内的合法坐标（含自身位置，含越界过滤）。"""
        out = []
        for ny in range(y - radius, y + radius + 1):
            for nx in range(x - radius, x + radius + 1):
                if self.in_bounds(nx, ny):
                    out.append((nx, ny))
        return out

    def candidate_moves(self, radius: int = 2) -> list[tuple[int, int]]:
        """候选落点 = 所有已落棋子的邻域中的空点（去重，按行序返回）。

        空盘无邻域可言，约定首手下天元。
        radius 越大越容易"跳"到远处的断点，代价是分支更多。
        """
        if not self.history:
            c = self.size // 2
            return [(c, c)]
        seen: set[tuple[int, int]] = set()
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != EMPTY:
                    for ny in range(max(0, y - radius), min(self.size, y + radius + 1)):
                        for nx in range(max(0, x - radius), min(self.size, x + radius + 1)):
                            if self.grid[ny][nx] == EMPTY:
                                seen.add((nx, ny))
        return sorted(seen, key=lambda p: (p[1], p[0]))

    # ---------- 其它 ----------

    def copy(self) -> Board:
        b = Board(self.size)
        b.grid = [row[:] for row in self.grid]
        b.history = list(self.history)
        return b

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Board size={self.size} moves={len(self.history)}>"
