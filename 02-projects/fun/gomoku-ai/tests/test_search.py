"""搜索测试：Alpha-Beta 与裸 Minimax 同分、取胜手、节点数、状态不被破坏。"""

import unittest

from gomoku import rules
from gomoku.board import BLACK, WHITE, Board
from gomoku.search import WIN_SCORE, search, search_once


def mid_game_board() -> Board:
    """12 手中局（与 demo c 同型），双方纠缠、分支较多。"""
    pos = [(7, 7, BLACK), (7, 8, WHITE), (8, 7, BLACK), (6, 7, WHITE),
           (8, 8, BLACK), (9, 7, WHITE), (6, 6, BLACK), (9, 9, WHITE),
           (5, 7, BLACK), (10, 8, WHITE), (9, 6, BLACK), (8, 6, WHITE)]
    b = Board()
    for x, y, p in pos:
        b.play(x, y, p)
    return b


class TestPruningCorrectness(unittest.TestCase):
    """剪枝正确性：Alpha-Beta 与裸 Minimax 在同一局面必须返回同分同着。"""

    def test_same_score_depth3(self):
        b = mid_game_board()
        ab = search_once(b, BLACK, depth=3, width=10)
        bare = search_once(b, BLACK, depth=3, width=10, bare=True)
        self.assertEqual(ab.score, bare.score)
        self.assertEqual(ab.move, bare.move)

    def test_same_score_depth4(self):
        b = mid_game_board()
        ab = search_once(b, BLACK, depth=4, width=10)
        bare = search_once(b, BLACK, depth=4, width=10, bare=True)
        self.assertEqual(ab.score, bare.score)
        self.assertEqual(ab.move, bare.move)

    def test_same_score_for_defending_side(self):
        """白方（后手）视角同样同分。"""
        b = mid_game_board()
        ab = search_once(b, WHITE, depth=3, width=10)
        bare = search_once(b, WHITE, depth=3, width=10, bare=True)
        self.assertEqual(ab.score, bare.score)

    def test_alpha_beta_visits_fewer_nodes(self):
        b = mid_game_board()
        ab = search_once(b, BLACK, depth=4, width=10)
        bare = search_once(b, BLACK, depth=4, width=10, bare=True)
        self.assertLess(ab.nodes, bare.nodes)
        self.assertGreater(ab.cutoffs, 0)


class TestWinFinding(unittest.TestCase):
    def test_immediate_five_is_played(self):
        """黑方四连一端开放 -> 必须直接成五。"""
        b = Board()
        for x in (5, 6, 7, 8):
            b.play(x, 7, BLACK)
        b.play(4, 7, WHITE)          # 封左端，黑可走 (9,7) 成五
        b.play(3, 3, WHITE)          # 白的闲着
        res = search_once(b, BLACK, depth=2, width=10)
        self.assertEqual(res.move, (9, 7))
        self.assertGreaterEqual(res.score, WIN_SCORE / 2)
        b.play(*res.move, BLACK)
        self.assertTrue(rules.is_five(b, *res.move, BLACK))

    def test_open_three_finds_forcing_win(self):
        """残局：黑方活三 -> AI 的着必须制造活四（两个杀点），随后必胜。"""
        b = Board()
        for x in (5, 6, 7):
            b.play(x, 7, BLACK)
        for x, y in ((10, 3), (11, 3)):
            b.play(x, y, WHITE)
        res = search_once(b, BLACK, depth=4, width=10)
        self.assertIsNotNone(res.move)
        self.assertGreaterEqual(res.score, WIN_SCORE / 2, "AI 未识别必胜分支")
        b.play(*res.move, BLACK)
        kills = rules.winning_squares(b, BLACK)
        self.assertGreaterEqual(len(kills), 2, "这一手没有形成活四（双杀）")
        # 白堵一个杀点，黑走另一个成五
        b.play(*kills[0], WHITE)
        b.play(*kills[1], BLACK)
        self.assertTrue(rules.is_five(b, *kills[1], BLACK))

    def test_search_never_mutates_board(self):
        b = mid_game_board()
        snapshot = [(x, y, p) for x, y, p in b.history]
        search_once(b, BLACK, depth=3, width=10)
        search(b, WHITE, depth=3, width=10)
        self.assertEqual(b.history, snapshot)
        self.assertEqual(len(b.empties()), 15 * 15 - len(snapshot))


class TestSearchApi(unittest.TestCase):
    def test_iterative_deepening_completes_requested_depth(self):
        b = mid_game_board()
        res = search(b, BLACK, depth=3, width=8)
        self.assertEqual(res.depth, 3)
        self.assertIsNotNone(res.move)
        self.assertGreater(res.nodes, 0)
        self.assertGreater(res.elapsed, 0.0)

    def test_time_limit_stops_early_but_returns_a_move(self):
        b = mid_game_board()
        res = search(b, BLACK, depth=12, width=12, time_limit=0.5)
        self.assertLess(res.depth, 12)          # 被时间预算截断
        self.assertIsNotNone(res.move)

    def test_move_is_legal_and_candidate(self):
        b = mid_game_board()
        res = search_once(b, BLACK, depth=3, width=10)
        x, y = res.move
        self.assertTrue(b.in_bounds(x, y))
        self.assertEqual(b.get(x, y), 0)
        self.assertIn(res.move, b.candidate_moves(radius=2))


if __name__ == "__main__":
    unittest.main()
