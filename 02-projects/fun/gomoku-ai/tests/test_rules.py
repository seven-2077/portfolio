"""五连胜负判定测试：全方向、边界安全、平局。"""

import unittest

from gomoku.board import BLACK, WHITE, Board
from gomoku import rules


class TestFiveInARow(unittest.TestCase):
    def test_five_horizontal(self):
        b = Board()
        for x in range(5):
            b.play(x, 7, BLACK)
        self.assertTrue(rules.is_five(b, 2, 7, BLACK))
        self.assertEqual(rules.find_winner(b), BLACK)

    def test_five_vertical(self):
        b = Board()
        for y in range(5):
            b.play(3, y, WHITE)
        self.assertTrue(rules.is_five(b, 3, 2, WHITE))
        self.assertEqual(rules.find_winner(b), WHITE)

    def test_five_diag_down(self):
        """主对角 \\ 方向。"""
        b = Board()
        for i in range(5):
            b.play(i, i, BLACK)
        self.assertTrue(rules.is_five(b, 4, 4, BLACK))
        self.assertFalse(rules.is_five(b, 3, 3, WHITE))  # 空点/对方不成立

    def test_five_diag_up(self):
        """副对角 / 方向。"""
        b = Board()
        for i in range(5):
            b.play(4 + i, 10 - i, BLACK)
        self.assertTrue(rules.is_five(b, 6, 8, BLACK))

    def test_five_at_corner_edge(self):
        """边界安全：贴着上边与左边连五。"""
        b = Board()
        for i in range(5):
            b.play(i, 0, BLACK)
        self.assertTrue(rules.is_five(b, 0, 0, BLACK))
        self.assertTrue(rules.is_five(b, 4, 0, BLACK))

    def test_five_vertical_at_last_column(self):
        b = Board()
        for y in range(5):
            b.play(14, 14 - y, WHITE)
        self.assertTrue(rules.is_five(b, 14, 14, WHITE))

    def test_four_is_not_five(self):
        b = Board()
        for x in range(4):
            b.play(x, 0, BLACK)
        self.assertFalse(rules.is_five(b, 0, 0, BLACK))
        self.assertIsNone(rules.find_winner(b))

    def test_long_run_counts_as_five(self):
        """六连同样判胜（>= 5）。"""
        b = Board()
        for x in range(6):
            b.play(x, 5, BLACK)
        self.assertTrue(rules.is_five(b, 0, 5, BLACK))
        self.assertTrue(rules.is_five(b, 5, 5, BLACK))


class TestDraw(unittest.TestCase):
    def _full_board_no_five(self) -> Board:
        """铺满全盘且四方向最大连续为 2：color = (x + 2y) mod 5 < 2。

        沿任一方向 f = (x+2y) mod 5 的步长为 1/2/3/4（均非 0 mod 5），
        五个连续位置里同色最多相邻两个 -> 不可能成五。
        """
        b = Board()
        for y in range(15):
            for x in range(15):
                player = BLACK if (x + 2 * y) % 5 < 2 else WHITE
                b.play(x, y, player)
        return b

    def test_full_board_without_five_is_draw(self):
        b = self._full_board_no_five()
        self.assertTrue(b.is_full())
        self.assertIsNone(rules.find_winner(b))
        self.assertTrue(rules.is_draw(b))

    def test_not_full_is_not_draw(self):
        b = Board()
        b.play(7, 7, BLACK)
        self.assertFalse(rules.is_draw(b))

    def test_check_result_win(self):
        b = Board()
        for x in range(5):
            b.play(x, 7, BLACK)
        self.assertEqual(rules.check_result(b), ("win", BLACK))

    def test_winning_squares_identify_kill_points(self):
        """冲四的杀点识别：黑四连一端被封 -> 恰好一个成五点。"""
        b = Board()
        for x in range(5, 9):
            b.play(x, 7, BLACK)
        b.play(4, 7, WHITE)          # 封住左端
        self.assertEqual(rules.winning_squares(b, BLACK), [(9, 7)])


if __name__ == "__main__":
    unittest.main()
