"""五连胜负判定与平局判定。

四个方向：横 (1,0)、竖 (0,1)、主对角 (1,1)、副对角 (1,-1)。
所有计数都先判边界，天然安全；五连及以上一律判胜。
"""

from __future__ import annotations

from .board import Board, EMPTY, PLAYERS

DIRECTIONS: tuple[tuple[int, int], ...] = ((1, 0), (0, 1), (1, 1), (1, -1))


def line_length(board: Board, x: int, y: int, player: int, dx: int, dy: int) -> int:
    """从 (x, y) 出发沿 (dx, dy) 双向延伸，返回该方向上 player 的连续棋子数。"""
    n = 1
    nx, ny = x + dx, y + dy
    while board.in_bounds(nx, ny) and board.get(nx, ny) == player:
        n += 1
        nx += dx
        ny += dy
    nx, ny = x - dx, y - dy
    while board.in_bounds(nx, ny) and board.get(nx, ny) == player:
        n += 1
        nx -= dx
        ny -= dy
    return n


def is_five(board: Board, x: int, y: int, player: int) -> bool:
    """判断 player 在 (x, y) 落子（或已有子）后，是否在任一方向连成五。"""
    if board.get(x, y) != player:
        return False
    return any(line_length(board, x, y, player, dx, dy) >= 5 for dx, dy in DIRECTIONS)


def find_winner(board: Board) -> int | None:
    """扫描全盘找五连（慢路径，供测试 / 复盘使用）。"""
    for y in range(board.size):
        for x in range(board.size):
            p = board.get(x, y)
            if p != EMPTY and is_five(board, x, y, p):
                return p
    return None


def winning_squares(board: Board, player: int) -> list[tuple[int, int]]:
    """返回 player 再落一子即可成五的所有空点（用于识别冲四/活四的杀点）。"""
    out: list[tuple[int, int]] = []
    for y in range(board.size):
        for x in range(board.size):
            if board.get(x, y) != EMPTY:
                continue
            if not board.play(x, y, player):
                continue
            if is_five(board, x, y, player):
                out.append((x, y))
            board.undo()
    return out


def is_draw(board: Board) -> bool:
    """平局 = 棋盘下满且全盘无五连。"""
    if not board.is_full():
        return False
    return find_winner(board) is None


def check_result(board: Board) -> tuple[str, int | None] | None:
    """最近一手后的终局检查。返回 ("win", player) / ("draw", None)，否则 None。"""
    if not board.history:
        return None
    x, y, player = board.history[-1]
    if is_five(board, x, y, player):
        return ("win", player)
    if is_full_and_no_five(board):
        return ("draw", None)
    return None


def is_full_and_no_five(board: Board) -> bool:
    return board.is_full() and find_winner(board) is None


def validate_player(player: int) -> bool:
    return player in PLAYERS
