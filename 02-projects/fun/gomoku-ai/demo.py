#!/usr/bin/env python3
"""演示脚本：三个 demo 一次跑完。

a) AI 制胜手：给定残局（己方活三），AI 必须找到取胜着，并验证后续必胜；
b) AI vs AI 自对弈，输出文本棋谱到 output/;
c) 同局面裸 Minimax vs Alpha-Beta 的节点访问数对比（分数必须一致）。

运行：python demo.py
"""

from __future__ import annotations

import time
from pathlib import Path

from gomoku import rules
from gomoku.board import BLACK, WHITE, Board
from gomoku.cli import coord_name, render
from gomoku.evaluate import evaluate
from gomoku.search import WIN_SCORE, search, search_once
from gomoku.selfplay import SideConfig, play_game, save_record

OUT_DIR = Path(__file__).resolve().parent / "output"


class Reporter:
    """打印并收集，最后落盘一份 demo 报告。"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def title(self, text: str) -> None:
        self.say()
        self.say("=" * 54)
        self.say(text)
        self.say("=" * 54)

    def save(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def _demo_board() -> Board:
    """残局：黑（AI）在第 8 行有一条活三 F8-G8-H8，白子散在右上。"""
    board = Board()
    for x in (5, 6, 7):          # 黑活三：F8 G8 H8
        board.play(x, 7, BLACK)
    for x, y in ((10, 3), (11, 3), (10, 4)):   # 白的弱结构
        board.play(x, y, WHITE)
    return board


def demo_winning_move(rep: Reporter) -> None:
    """a) 残局取胜着：己方活三 -> 活四 -> 必胜。"""
    rep.title("a) AI 制胜手：己方活三，找出取胜着")
    board = _demo_board()
    rep.say("局面（黑先行，黑有活三 F8-G8-H8）：")
    rep.say(render(board, reverse=False))
    rep.say(f"静态评估（黑视角）：{evaluate(board, BLACK):+.0f}")

    t0 = time.perf_counter()
    res = search(board, BLACK, depth=4, width=10)
    elapsed = time.perf_counter() - t0
    assert res.move is not None, "AI 没有给出着法"
    rep.say(f"\nAI 落子：{coord_name(*res.move)}   评估 {res.score:+.0f}"
            f"（{res.verdict}）  节点 {res.nodes}  用时 {elapsed:.2f}s")

    # —— 验证 1：这一手必须制造"活四"（两个杀点，堵一个我走另一个）——
    board.play(*res.move, BLACK)
    rep.say(f"\n落子后棋盘（反色为最新一手）：")
    rep.say(render(board, board.last_move))
    kills = rules.winning_squares(board, BLACK)
    rep.say(f"黑再走一步即可成五的杀点：{[coord_name(*k) for k in kills]}")
    assert len(kills) >= 2, f"AI 没有走出活四（杀点只有 {len(kills)} 个）"
    assert res.score >= WIN_SCORE / 2, "AI 没有识别出必胜分支"

    # —— 验证 2：白堵一个杀点，黑走另一个，成五 ——
    block, follow = kills[0], kills[1]
    board.play(*block, WHITE)
    rep.say(f"白方堵杀点 {coord_name(*block)}，黑方走 {coord_name(*follow)} ...")
    board.play(*follow, BLACK)
    assert rules.is_five(board, *follow, BLACK), "后续没有成五！"
    rep.say(render(board, board.last_move))
    rep.say("-> 黑方五连获胜，取胜着验证通过 ✓")


def demo_selfplay(rep: Reporter) -> None:
    """b) AI vs AI 自对弈，棋谱写入 output/。"""
    rep.title("b) AI vs AI 自对弈，生成文本棋谱")
    black = SideConfig(depth=4, width=10)
    white = SideConfig(depth=4, width=10)
    rep.say(f"黑方 {black.label()}  vs  白方 {white.label()}")
    t0 = time.perf_counter()
    rec = play_game(black, white)
    elapsed = time.perf_counter() - t0

    board = Board()
    for x, y, p in rec.moves:
        board.play(x, y, p)
    path = save_record(rec, OUT_DIR, final_board=board)

    who = f"{'黑' if rec.winner == BLACK else '白'}胜" if rec.winner else "平局"
    rep.say(f"终局：{who}（{rec.end_reason}），共 {len(rec.moves)} 手，"
            f"用时 {elapsed:.1f}s")
    head = "  ".join(f"{i}. {'黑' if p == BLACK else '白'} {coord_name(x, y)}"
                     for i, (x, y, p) in enumerate(rec.moves[:10], 1))
    rep.say(f"开局前 10 手：{head} ...")
    rep.say(f"棋谱路径：{path}")
    rep.say()
    rep.say("\n".join(path.read_text(encoding="utf-8").splitlines()[:14]))


def demo_pruning(rep: Reporter) -> None:
    """c) 同局面：裸 Minimax vs Alpha-Beta 节点数对比。"""
    rep.title("c) 裸 Minimax vs Alpha-Beta：同局面节点访问数对比")
    pos = [(7, 7, BLACK), (7, 8, WHITE), (8, 7, BLACK), (6, 7, WHITE),
           (8, 8, BLACK), (9, 7, WHITE), (6, 6, BLACK), (9, 9, WHITE),
           (5, 7, BLACK), (10, 8, WHITE), (9, 6, BLACK), (8, 6, WHITE)]
    board = Board()
    for x, y, p in pos:
        board.play(x, y, p)
    rep.say("中局局面（12 手，黑先行）：")
    rep.say(render(board, reverse=False))

    depth, width = 4, 10
    t0 = time.perf_counter()
    bare = search_once(board, BLACK, depth=depth, width=width, bare=True)
    t_bare = time.perf_counter() - t0
    t0 = time.perf_counter()
    ab = search_once(board, BLACK, depth=depth, width=width)
    t_ab = time.perf_counter() - t0

    rep.say()
    rep.say(f"{'':14}{'节点数':>10}{'截断数':>10}{'耗时':>10}{'评估分':>14}")
    rep.say(f"{'裸 Minimax':14}{bare.nodes:>10}{'-':>10}"
            f"{t_bare:>9.2f}s{bare.score:>+14.0f}")
    rep.say(f"{'Alpha-Beta':14}{ab.nodes:>10}{ab.cutoffs:>10}"
            f"{t_ab:>9.2f}s{ab.score:>+14.0f}")
    ratio = bare.nodes / max(ab.nodes, 1)
    rep.say(f"\n节点缩减 {ratio:.1f}x，耗时缩减 {t_bare / max(t_ab, 1e-9):.1f}x"
            f"（深度 {depth}，候选宽度 {width}）")
    rep.say(f"两者评估分一致：{bare.score:+.0f} == {ab.score:+.0f}"
            f" -> {'True' if bare.score == ab.score else 'False'}")

    assert bare.score == ab.score, "剪枝改变了返回分数！"
    assert bare.move == ab.move, "剪枝改变了最优着法！"
    assert ab.nodes < bare.nodes, "剪枝没有减少节点！"
    rep.say("-> Alpha-Beta 与裸 Minimax 同分同着，剪枝正确且更快 ✓")


def main() -> None:
    rep = Reporter()
    rep.say("五子棋 AI demo —— Minimax + Alpha-Beta 剪枝")
    rep.say(f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    demo_winning_move(rep)
    demo_selfplay(rep)
    demo_pruning(rep)
    rep.title("全部 demo 通过 ✓")
    OUT_DIR.mkdir(exist_ok=True)
    report_path = OUT_DIR / "demo_report.txt"
    rep.save(report_path)
    print(f"\n报告已写入：{report_path}")


if __name__ == "__main__":
    main()
