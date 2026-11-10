"""终端人机对战：棋盘渲染、坐标解析、难度档、AI 耗时打印。

坐标约定（两种输入等价）：
    H8  = 列 H（第 8 列）、行 8      -> (x=7, y=7)
    8,8 = 第 8 列、第 8 行           -> (x=7, y=7)
列用字母 A-O，行用数字 1-15（自上而下），与棋盘打印一致。
"""

from __future__ import annotations

import re
import time

from . import rules
from .board import BLACK, EMPTY, SIZE, WHITE, Board
from .search import search

COLS = "ABCDEFGHIJKLMNO"

# 难度档 = (名称, 深度, 候选宽度, 时间预算秒)
TIERS: dict[str, tuple[str, int, int, float | None]] = {
    "1": ("浅", 2, 6, None),
    "2": ("中", 4, 10, None),
    "3": ("深", 6, 12, 10.0),
}

_STONE = {BLACK: "●", WHITE: "○"}


def render(board: Board, last: tuple[int, int] | None = None,
           reverse: bool = True) -> str:
    """渲染棋盘：数字行号 + 字母列标，最新一手反色高亮。"""
    header = "     " + " ".join(COLS)
    rows = [header]
    for y in range(board.size):
        cells = []
        for x in range(board.size):
            v = board.get(x, y)
            ch = "·" if v == EMPTY else _STONE[v]
            if last == (x, y) and reverse:
                ch = f"\033[7m{ch}\033[0m"
            cells.append(ch)
        rows.append(f"{y + 1:2d}   " + " ".join(cells))
    rows.append("     " + " ".join(COLS))
    return "\n".join(rows)


def parse_coord(text: str, size: int = SIZE) -> tuple[int, int] | None:
    """解析 'H8' 或 '8,8'（1-based 列行）。无法解析返回 None。"""
    s = text.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z])(\d{1,2})", s)
    if m:
        x = COLS.index(m.group(1)) if m.group(1) in COLS else -1
        y = int(m.group(2)) - 1
    else:
        m = re.fullmatch(r"(\d{1,2}),(\d{1,2})", s)
        if not m:
            return None
        x, y = int(m.group(1)) - 1, int(m.group(2)) - 1
    if 0 <= x < size and 0 <= y < size:
        return (x, y)
    return None


def coord_name(x: int, y: int) -> str:
    return f"{COLS[x]}{y + 1}"


def _ask_tier() -> tuple[str, int, int, float | None]:
    print("\n选择难度：  [1] 浅（深度2）  [2] 中（深度4）  [3] 深（深度6，限时10s）")
    while True:
        choice = input("难度 [2]: ").strip() or "2"
        if choice in TIERS:
            name, depth, width, limit = TIERS[choice]
            print(f"已选「{name}」档。")
            return name, depth, width, limit
        print("请输入 1 / 2 / 3。")


def _announce(result: tuple[str, int | None], human: int) -> None:
    kind, player = result
    if kind == "win":
        who = "你" if player == human else "AI"
        print(f"\n*** {who}（{_STONE[player]}）五连获胜！***")
    else:
        print("\n*** 棋盘下满，平局。***")


def main() -> None:
    print("=" * 46)
    print("  终端五子棋 AI  —— Minimax + Alpha-Beta 剪枝")
    print("  你执黑先行。输入坐标落子，如 H8 或 8,8；q 退出。")
    print("=" * 46)

    tier_name, depth, width, limit = _ask_tier()
    board = Board()
    human, ai = BLACK, WHITE

    while True:
        print()
        print(render(board, board.last_move))
        result = rules.check_result(board)
        if result:
            _announce(result, human)
            break

        text = input("\n你的落子 > ").strip()
        if text.lower() in ("q", "quit", "exit"):
            print("再见。")
            break
        coord = parse_coord(text)
        if coord is None:
            print("无法识别，请输入如 H8 / 8,8 的坐标，或 q 退出。")
            continue
        if not board.play(*coord, human):
            print("该位置不可落子，换一个试试。")
            continue

        result = rules.check_result(board)
        if result:
            print(render(board, board.last_move))
            _announce(result, human)
            break

        # ---------- AI 回合 ----------
        res = search(board, ai, depth=depth, width=width, time_limit=limit)
        assert res.move is not None
        board.play(*res.move, ai)
        print(f"AI（{tier_name}档·深度{res.depth}）落子 {coord_name(*res.move)}"
              f"，用时 {res.elapsed:.2f}s，访问 {res.nodes} 节点"
              f"，评估 {res.score:+.0f}（{res.verdict}）")

        result = rules.check_result(board)
        if result:
            print(render(board, board.last_move))
            _announce(result, human)
            break


if __name__ == "__main__":  # pragma: no cover
    main()
