"""棋盘状态测试：落子/提子、非法操作、候选走法生成（含半径）。"""

import unittest

from gomoku.board import BLACK, EMPTY, WHITE, Board


class TestPlayUndo(unittest.TestCase):
    def test_play_then_undo_restores_state(self):
        b = Board()
        self.assertTrue(b.play(7, 7, BLACK))
        self.assertEqual(b.get(7, 7), BLACK)
        self.assertEqual(b.last_move, (7, 7))
        undone = b.undo()
        self.assertEqual(undone, (7, 7, BLACK))
        self.assertEqual(b.get(7, 7), EMPTY)
        self.assertEqual(b.history, [])
        self.assertIsNone(b.undo())          # 空栈再悔棋安全

    def test_undo_pops_in_reverse_order(self):
        b = Board()
        b.play(1, 1, BLACK)
        b.play(2, 2, WHITE)
        self.assertEqual(b.undo(), (2, 2, WHITE))
        self.assertEqual(b.undo(), (1, 1, BLACK))
        self.assertEqual(b.get(1, 1), EMPTY)
        self.assertEqual(b.get(2, 2), EMPTY)

    def test_play_rejects_invalid_moves(self):
        b = Board()
        self.assertFalse(b.play(99, 0, BLACK))       # 越界
        self.assertFalse(b.play(0, -1, WHITE))       # 越界
        self.assertFalse(b.play(0, 0, 3))            # 非法棋手
        self.assertTrue(b.play(0, 0, BLACK))
        self.assertFalse(b.play(0, 0, WHITE))        # 占位
        self.assertEqual(len(b.history), 1)

    def test_copy_is_independent(self):
        b = Board()
        b.play(3, 3, BLACK)
        c = b.copy()
        c.play(4, 4, WHITE)
        self.assertEqual(b.get(4, 4), EMPTY)
        self.assertEqual(len(b.history), 1)
        self.assertEqual(len(c.history), 2)


class TestMoveGeneration(unittest.TestCase):
    def test_empty_board_candidate_is_center(self):
        b = Board()
        self.assertEqual(b.candidate_moves(radius=2), [(7, 7)])

    def test_candidate_is_stone_neighborhood(self):
        b = Board()
        b.play(7, 7, BLACK)
        cands = set(b.candidate_moves(radius=1))
        # 半径 1 = 3x3 邻域去掉已占中心
        expected = {(x, y) for x in range(6, 9) for y in range(6, 9)} - {(7, 7)}
        self.assertEqual(cands, expected)

    def test_radius_parameter_widens_candidates(self):
        b = Board()
        b.play(7, 7, BLACK)
        r1 = set(b.candidate_moves(radius=1))
        r2 = set(b.candidate_moves(radius=2))
        self.assertTrue(r1 < r2)                     # 真包含
        self.assertIn((9, 9), r2)                    # 切比雪夫距离 2
        self.assertNotIn((9, 9), r1)
        self.assertNotIn((11, 11), r2)               # 距离 4 不在半径 2 内

    def test_candidate_excludes_occupied_and_out_of_bounds(self):
        b = Board()
        b.play(0, 0, BLACK)
        b.play(14, 14, WHITE)
        cands = set(b.candidate_moves(radius=2))
        self.assertNotIn((0, 0), cands)
        self.assertNotIn((14, 14), cands)
        self.assertTrue(all(0 <= x < 15 and 0 <= y < 15 for x, y in cands))
        # 角落棋子的邻域只保留界内部分
        self.assertIn((1, 1), cands)
        self.assertIn((13, 13), cands)

    def test_neighbors_respect_bounds(self):
        b = Board()
        nb = b.neighbors(0, 0, radius=2)
        self.assertEqual(set(nb), {(x, y) for x in range(3) for y in range(3)})

    def test_candidate_deterministic_order(self):
        b = Board()
        b.play(7, 7, BLACK)
        b.play(3, 11, WHITE)
        self.assertEqual(b.candidate_moves(radius=2), b.candidate_moves(radius=2))


if __name__ == "__main__":
    unittest.main()
