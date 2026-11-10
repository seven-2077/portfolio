"""Minimax（Negamax 形式）+ Alpha-Beta 剪枝 + 迭代加深。

为什么写成 Negamax：五子棋是零和对称博弈，"我方视角的最优值 = -(对方视角的最优值)"，
于是同一套递归换个符号就能交替求解，代码只有一份。

Alpha-Beta 与裸 Minimax 返回同分的直觉：被剪掉的分支，其取值无论如何都落在
(alpha, beta) 窗口之外，不可能改变任何上层 max/min 的选择——剪枝只砍"注定没用"的枝，
不改变根节点的最小最大值。收益是访问节点数从 O(b^d) 降到理想 O(b^(d/2))。

候选点按静态评分排序（preview_score）不是为了"更聪明"，而是为了剪枝效率：
最强的着先走，alpha 抬得快，后面兄弟子树整片被剪掉。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import rules
from .board import Board, opponent
from .evaluate import Evaluator, preview_score

WIN_SCORE = 1_000_000_000      # 必胜分：远大于任何棋型评估分（上限约 2e8）
INF = float("inf")


@dataclass
class SearchResult:
    move: tuple[int, int] | None
    score: float
    depth: int                  # 实际完成的搜索深度
    nodes: int                  # 访问节点总数（含各层迭代加深）
    cutoffs: int                # Alpha-Beta 截断次数
    elapsed: float              # 秒
    bare: bool = False          # 是否为裸 Minimax（无剪枝，用于对比）

    @property
    def verdict(self) -> str:
        if self.score >= WIN_SCORE / 2:
            return "必胜"
        if self.score <= -WIN_SCORE / 2:
            return "必败"
        return "均势"


@dataclass
class _Ctx:
    nodes: int = 0
    cutoffs: int = 0


def ordered_moves(board: Board, ev: Evaluator, player: int,
                  radius: int = 2, width: int | None = None) -> list[tuple[int, int]]:
    """候选点生成 + 静态评分排序（强着在前），可截取前 width 个。"""
    cands = board.candidate_moves(radius)
    if not cands:                       # 邻域占满但棋盘未满：退回全空点
        cands = board.empties()
    ranked = sorted(
        ((preview_score(board, x, y, player), y, x) for x, y in cands),
        reverse=True,
    )
    moves = [(x, y) for _, y, x in ranked]
    return moves[:width] if width else moves


def _negamax(board: Board, ev: Evaluator, player: int, depth: int,
             alpha: float, beta: float, ctx: _Ctx,
             radius: int, width: int | None,
             use_ab: bool) -> tuple[float, tuple[int, int] | None]:
    """返回 (该局面下 player 视角的最优分, 最优着法)。use_ab=False 即裸 Minimax。"""
    ctx.nodes += 1
    if depth <= 0:
        return ev.evaluate(player), None

    moves = ordered_moves(board, ev, player, radius, width)
    if not moves:
        # 无候选：棋盘满为平局（0 分），否则按静态评估作叶子
        return (0.0 if board.is_full() else ev.evaluate(player)), None

    best_score = -INF
    best_move = moves[0]
    for move in moves:
        x, y = move
        board.play(x, y, player)
        ev.refresh(x, y)
        if rules.is_five(board, x, y, player):
            # 胜负短路：立刻成五即该节点理论最高分（越快赢分越高）
            score = WIN_SCORE - len(board.history)
        else:
            sub, _ = _negamax(board, ev, opponent(player), depth - 1,
                              -beta, -alpha, ctx, radius, width, use_ab)
            score = -sub
        board.undo()
        ev.refresh(x, y)

        if score > best_score:
            best_score, best_move = score, move
        if use_ab:
            if best_score > alpha:
                alpha = best_score
            if alpha >= beta:           # 兄弟子树全部无须再看
                ctx.cutoffs += 1
                break
    return best_score, best_move


def search_once(board: Board, player: int, depth: int = 4,
                width: int | None = 10, radius: int = 2,
                bare: bool = False) -> SearchResult:
    """单深度搜索（不迭代加深）。demo 的剪枝对比、单元测试都用它，保证口径一致。"""
    t0 = time.perf_counter()
    ev = Evaluator(board)
    ctx = _Ctx()
    score, move = _negamax(board, ev, player, depth, -INF, INF, ctx,
                           radius, width, use_ab=not bare)
    return SearchResult(move=move, score=score, depth=depth, nodes=ctx.nodes,
                        cutoffs=ctx.cutoffs, elapsed=time.perf_counter() - t0,
                        bare=bare)


def search(board: Board, player: int, depth: int = 4,
           width: int | None = 10, radius: int = 2,
           time_limit: float | None = None, bare: bool = False) -> SearchResult:
    """迭代加深搜索：1..depth 逐层加深，超时则保留最后一层完成的结果。

    迭代加深的两个好处：小深度结果先兜底（不会返回半途而废的残缺解），
    且天然适配"时间预算"式难度控制。
    """
    depth = max(1, depth)
    t0 = time.perf_counter()
    total_nodes = 0
    total_cutoffs = 0
    result: SearchResult | None = None
    for d in range(1, depth + 1):
        r = search_once(board, player, d, width, radius, bare)
        total_nodes += r.nodes
        total_cutoffs += r.cutoffs
        result = SearchResult(move=r.move, score=r.score, depth=d,
                              nodes=total_nodes, cutoffs=total_cutoffs,
                              elapsed=time.perf_counter() - t0, bare=bare)
        if time_limit is not None and result.elapsed >= time_limit:
            break
    assert result is not None
    return result
