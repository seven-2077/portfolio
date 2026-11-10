"""AI vs AI 自动对局：落子序列记录为文本棋谱，写入 output/。

用法：
    python -m gomoku.selfplay                    # 默认双方中档（深度4）
    python -m gomoku.selfplay --black-depth 4 --white-depth 3 --out output
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import rules
from .board import BLACK, WHITE, Board
from .cli import render
from .search import search

DEFAULT_DEPTH = 4
DEFAULT_WIDTH = 10


@dataclass
class SideConfig:
    depth: int = DEFAULT_DEPTH
    width: int = DEFAULT_WIDTH
    time_limit: float | None = None

    def label(self) -> str:
        return f"depth={self.depth} width={self.width}"


@dataclass
class GameRecord:
    black: SideConfig
    white: SideConfig
    moves: list[tuple[int, int, int]] = field(default_factory=list)  # (x, y, player)
    winner: int | None = None
    end_reason: str = ""
    started_at: str = ""
    elapsed: float = 0.0


def coord_name(x: int, y: int) -> str:
    from .cli import COLS
    return f"{COLS[x]}{y + 1}"


def play_game(black: SideConfig | None = None, white: SideConfig | None = None,
              verbose: bool = False) -> GameRecord:
    """黑先，双方轮流用 search 落子，直到分出胜负或平局。"""
    black = black or SideConfig()
    white = white or SideConfig()
    board = Board()
    rec = GameRecord(black=black, white=white,
                     started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    t0 = time.perf_counter()

    while True:
        # 黑先：历史偶数手（0-based）轮到黑
        player = BLACK if len(board.history) % 2 == 0 else WHITE
        cfg = black if player == BLACK else white
        res = search(board, player, depth=cfg.depth, width=cfg.width,
                     time_limit=cfg.time_limit)
        if res.move is None:
            rec.end_reason = "平局(无候选点)"
            break
        board.play(*res.move, player)
        rec.moves.append((res.move[0], res.move[1], player))
        if verbose:
            side = "黑" if player == BLACK else "白"
            print(f"  {len(rec.moves):3d}. {side} {coord_name(*res.move)}"
                  f"  score={res.score:+.0f} nodes={res.nodes} {res.elapsed:.2f}s")
        result = rules.check_result(board)
        if result:
            kind, who = result
            rec.winner = who if kind == "win" else None
            rec.end_reason = "五连" if kind == "win" else "平局"
            break

    rec.elapsed = time.perf_counter() - t0
    return rec


def format_record(rec: GameRecord, final_board: Board | None = None) -> str:
    """把对局记录渲染成文本棋谱。"""
    lines = [
        "# 五子棋 AI 自对弈棋谱",
        f"# 时间: {rec.started_at}",
        f"# 黑方: {rec.black.label()}   白方: {rec.white.label()}",
        "# 结果: " + (f"{'黑' if rec.winner == BLACK else '白'}胜（{rec.end_reason}）"
                    if rec.winner else rec.end_reason),
        f"# 手数: {len(rec.moves)}   用时: {rec.elapsed:.1f}s",
        "",
    ]
    row: list[str] = []
    for i, (x, y, player) in enumerate(rec.moves, 1):
        side = "黑" if player == BLACK else "白"
        row.append(f"{i:3d}. {side} {coord_name(x, y)}")
        if len(row) == 5:
            lines.append("  ".join(row))
            row = []
    if row:
        lines.append("  ".join(row))
    if final_board is not None:
        lines += ["", "# 终局棋盘:",
                  render(final_board, final_board.last_move, reverse=False)]
    return "\n".join(lines) + "\n"


def save_record(rec: GameRecord, out_dir: str | Path = "output",
                final_board: Board | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"selfplay_{stamp}.txt"
    path.write_text(format_record(rec, final_board), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="五子棋 AI 自对弈，输出文本棋谱")
    p.add_argument("--black-depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--white-depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="每节点候选宽度")
    p.add_argument("--out", default="output", help="棋谱输出目录")
    p.add_argument("--verbose", action="store_true", help="逐手打印")
    args = p.parse_args(argv)

    black = SideConfig(depth=args.black_depth, width=args.width)
    white = SideConfig(depth=args.white_depth, width=args.width)
    print(f"开局：黑 {black.label()} vs 白 {white.label()} ...")
    rec = play_game(black, white, verbose=args.verbose)
    board = Board()
    for x, y, player in rec.moves:
        board.play(x, y, player)
    path = save_record(rec, args.out, final_board=board)
    who = f"{'黑' if rec.winner == BLACK else '白'}胜" if rec.winner else "平局"
    print(f"终局：{who}（{rec.end_reason}），共 {len(rec.moves)} 手，"
          f"用时 {rec.elapsed:.1f}s")
    print(f"棋谱已写入: {path}")


if __name__ == "__main__":  # pragma: no cover
    main()
