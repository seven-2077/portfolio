"""模式评分测试：棋型计数（活三/冲四/活四）、分值序、镜像对称、增量评估。"""

import unittest

from gomoku.board import BLACK, WHITE, Board
from gomoku.evaluate import (PATTERN_TABLE, SCORES, Evaluator, _map_line,
                             count_patterns, evaluate, line_value)
from gomoku.evaluate import LINES


def board_counts(board: Board, player: int) -> dict[str, int]:
    """汇总全盘所有线上的棋型计数（测试辅助）。"""
    totals = {name: 0 for name, _ in PATTERN_TABLE}
    for line in LINES:
        cells = tuple(board.get(x, y) for x, y in line)
        for name, n in count_patterns(_map_line(cells, player)).items():
            totals[name] += n
    return totals


def mirror_horizontal(board: Board) -> Board:
    m = Board()
    for y in range(board.size):
        for x in range(board.size):
            v = board.get(x, y)
            if v:
                m.play(board.size - 1 - x, y, v)
    return m


class TestPatternCounting(unittest.TestCase):
    def test_isolated_open_three(self):
        """空盘上一条孤立活三：活三 == 1，冲四/活四 == 0。"""
        b = Board()
        for x in (5, 6, 7):
            b.play(x, 7, BLACK)
        counts = board_counts(b, BLACK)
        self.assertEqual(counts["open_three"], 1)
        self.assertEqual(counts["four"], 0)
        self.assertEqual(counts["open_four"], 0)
        self.assertEqual(counts["five"], 0)
        # 白方没有任何棋型
        self.assertEqual(sum(board_counts(b, WHITE).values()), 0)

    def test_blocked_four_counts_once(self):
        """黑四连、一端被白封 -> 冲四恰好 1，不重复计为活四。"""
        b = Board()
        for x in (5, 6, 7, 8):
            b.play(x, 7, BLACK)
        b.play(9, 7, WHITE)
        counts = board_counts(b, BLACK)
        self.assertEqual(counts["four"], 1)
        self.assertEqual(counts["open_four"], 0)
        self.assertEqual(counts["five"], 0)

    def test_open_four_counts_once(self):
        """活四计 1，且其石子不被低级棋型重复计分。"""
        b = Board()
        for x in (5, 6, 7, 8):
            b.play(x, 7, BLACK)
        counts = board_counts(b, BLACK)
        self.assertEqual(counts["open_four"], 1)
        self.assertEqual(counts["four"], 0)
        self.assertEqual(counts["open_three"], 0)

    def test_five_beats_all_lower_patterns(self):
        b = Board()
        for x in (5, 6, 7, 8, 9):
            b.play(x, 7, BLACK)
        counts = board_counts(b, BLACK)
        self.assertEqual(counts["five"], 1)
        for name in ("open_four", "four", "open_three", "three"):
            self.assertEqual(counts[name], 0, name)

    def test_sleep_three_vs_open_three(self):
        """眠三（靠墙夹死一端）与活三的区分。"""
        self.assertEqual(count_patterns("2011102")["three"], 1)
        self.assertEqual(count_patterns("2011102")["open_three"], 0)
        self.assertEqual(count_patterns("0011100")["open_three"], 1)
        self.assertEqual(count_patterns("0011100")["three"], 0)

    def test_counting_is_reversal_symmetric(self):
        """模式表左右成对 + 顺序无关规则 => 行反向计数不变（镜像对称的基础）。"""
        samples = [
            "011110", "2111102", "0011100", "2011102", "1110110",
            "01011010110", "111011101110", "01100110", "1010101010",
            "20111011102", "0111011100",
        ]
        for s in samples:
            self.assertEqual(count_patterns(s), count_patterns(s[::-1]), s)


class TestScores(unittest.TestCase):
    def test_score_table_strictly_descending(self):
        """威胁等级越高分值越大（活五 > 活四 > 冲四 > 活三 > 眠三 > 活二 > 眠二）。"""
        values = list(SCORES.values())
        for a, b in zip(values, values[1:]):
            self.assertGreater(a, b)
        self.assertEqual(
            list(SCORES),
            ["five", "open_four", "four", "open_three", "three", "open_two", "two"],
        )

    def test_line_value_reflects_pattern_strength(self):
        # 棋格元组：0=空，1=黑，2=白（'2' 位即对方/边界）
        five = (1, 1, 1, 1, 1)
        open_four = (0, 1, 1, 1, 1, 0)
        one_side_four = (0, 1, 1, 1, 1, 2)   # 冲四：一端开放、一端被封
        open_three = (0, 0, 1, 1, 1, 0, 0)
        self.assertGreater(line_value(five, BLACK), line_value(open_four, BLACK))
        self.assertGreater(line_value(open_four, BLACK), line_value(one_side_four, BLACK))
        self.assertGreater(line_value(one_side_four, BLACK), line_value(open_three, BLACK))


class TestEvaluate(unittest.TestCase):
    def _asym_board(self) -> Board:
        b = Board()
        for x, y, p in ((5, 7, BLACK), (6, 7, BLACK), (7, 7, BLACK),
                        (10, 3, WHITE), (11, 3, WHITE), (10, 4, WHITE)):
            b.play(x, y, p)
        return b

    def test_mirror_symmetry_horizontal(self):
        b = self._asym_board()
        m = mirror_horizontal(b)
        self.assertEqual(evaluate(b, BLACK), evaluate(m, BLACK))
        self.assertEqual(evaluate(b, WHITE), evaluate(m, WHITE))

    def test_mirror_symmetry_vertical(self):
        b = self._asym_board()
        m = Board()
        for y in range(15):
            for x in range(15):
                v = b.get(x, y)
                if v:
                    m.play(x, 14 - y, v)
        self.assertEqual(evaluate(b, BLACK), evaluate(m, BLACK))

    def test_perspective_is_antisymmetric(self):
        b = self._asym_board()
        self.assertEqual(evaluate(b, BLACK), -evaluate(b, WHITE))

    def test_incremental_eval_matches_full_eval(self):
        b = Board()
        ev = Evaluator(b)
        moves = [(7, 7, BLACK), (7, 8, WHITE), (8, 7, BLACK), (6, 7, WHITE),
                 (8, 8, BLACK), (9, 7, WHITE), (6, 6, BLACK)]
        for x, y, p in moves:
            b.play(x, y, p)
            ev.refresh(x, y)
            for player in (BLACK, WHITE):
                self.assertAlmostEqual(ev.evaluate(player),
                                       evaluate(b, player), places=9)
        # 全部提子后应回到空盘评估
        while b.history:
            x, y, p = b.undo()
            ev.refresh(x, y)
        for player in (BLACK, WHITE):
            self.assertEqual(ev.evaluate(player), evaluate(b, player))
            self.assertEqual(ev.evaluate(player), 0.0)

    def test_empty_board_eval_is_zero(self):
        b = Board()
        self.assertEqual(evaluate(b, BLACK), 0.0)
        self.assertEqual(evaluate(b, WHITE), 0.0)


if __name__ == "__main__":
    unittest.main()
