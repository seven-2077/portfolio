"""B3/S23 规则引擎测试：规则边界、滑翔机平移、字符画往返。"""

import unittest

from lifelab.game_of_life import GameOfLife


class TestRuleBoundaries(unittest.TestCase):
    """孤独死亡 / 三邻居繁衍 / 拥挤死亡的边界格。"""

    def test_birth_requires_exactly_three(self):
        born = GameOfLife(5, 5, [(0, 1), (1, 0), (2, 1)])
        born.step()
        self.assertIn((1, 1), born)

        two = GameOfLife(5, 5, [(0, 1), (2, 1)])
        two.step()
        self.assertNotIn((1, 1), two)

        four = GameOfLife(5, 5, [(0, 1), (2, 1), (1, 0), (1, 2)])
        four.step()
        self.assertNotIn((1, 1), four)

    def test_loneliness_death(self):
        g = GameOfLife(5, 5, [(1, 1), (0, 1)])
        g.step()
        self.assertNotIn((1, 1), g)
        self.assertNotIn((0, 1), g)

    def test_overcrowding_death(self):
        g = GameOfLife(5, 5, [(1, 1), (0, 1), (2, 1), (1, 0), (1, 2)])
        g.step()
        self.assertNotIn((1, 1), g)

    def test_survival_with_two_and_three_neighbors(self):
        # 2 邻居：蜂鸣器中格存活，整体转竖
        blinker = [(1, 2), (2, 2), (3, 2)]
        b = GameOfLife(5, 5, blinker)
        b.step()
        self.assertEqual(b.live_cells, frozenset([(2, 1), (2, 2), (2, 3)]))
        # 3 邻居：方块（still life）原样存活
        block = [(0, 0), (1, 0), (0, 1), (1, 1)]
        s = GameOfLife(5, 5, block)
        s.step()
        self.assertEqual(s.live_cells, frozenset(block))


class TestGlider(unittest.TestCase):
    """滑翔机：4 代一周期，平移 (1,1)，population 恒为 5。"""

    CELLS = frozenset([(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)])

    def test_four_steps_translate_one_cell(self):
        g = GameOfLife(12, 12, self.CELLS)
        g.run(4)
        self.assertEqual(
            g.live_cells,
            frozenset((x + 1, y + 1) for x, y in self.CELLS),
        )

    def test_eight_steps_translate_two_cells(self):
        g = GameOfLife(12, 12, self.CELLS)
        g.run(8)
        self.assertEqual(
            g.live_cells,
            frozenset((x + 2, y + 2) for x, y in self.CELLS),
        )

    def test_population_conserved_every_step(self):
        g = GameOfLife(12, 12, self.CELLS)
        for _ in range(16):
            g.step()
            self.assertEqual(g.population, 5)


class TestSerialization(unittest.TestCase):
    """图案加载往返：text → cells → text 稳定。"""

    def test_roundtrip_glider(self):
        text = ".O.\n..O\nOOO"
        g = GameOfLife.from_text(text)
        self.assertEqual(g.to_text(), text)
        again = GameOfLife.from_text(g.to_text())
        self.assertEqual(again.live_cells, g.live_cells)
        self.assertEqual((again.width, again.height), (g.width, g.height))

    def test_roundtrip_after_evolution(self):
        g = GameOfLife.from_text("...\nOOO\n...")
        g.run(7)
        # 不裁剪：绝对坐标逐一保持
        exact = g.to_text(trim=False)
        self.assertEqual(GameOfLife.from_text(exact).live_cells, g.live_cells)
        # 裁剪：规范形稳定（允许整体平移到包围盒原点）
        canonical = g.to_text()
        self.assertTrue(canonical)
        self.assertEqual(GameOfLife.from_text(canonical).to_text(), canonical)

    def test_from_text_skips_blank_lines_and_indent(self):
        text = "\n    .O.\n    ..O\n    OOO\n\n"
        g = GameOfLife.from_text(text)
        self.assertEqual(g.population, 5)
        self.assertEqual(g.to_text(), ".O.\n..O\nOOO")

    def test_ragged_rows_pad_dead(self):
        g = GameOfLife.from_text("OO\n....")
        self.assertEqual((g.width, g.height), (4, 2))
        self.assertEqual(g.population, 2)
        self.assertNotIn((3, 0), g)

    def test_unknown_char_raises(self):
        with self.assertRaises(ValueError):
            GameOfLife.from_text("O?O")
        with self.assertRaises(ValueError):
            GameOfLife.from_text("   ")

    def test_to_text_empty_grid(self):
        self.assertEqual(GameOfLife(5, 5).to_text(), "")


class TestGrid(unittest.TestCase):
    def test_population_and_bbox(self):
        g = GameOfLife(10, 10, [(0, 0), (5, 5)])
        self.assertEqual(g.population, 2)
        self.assertEqual(g.bbox(), (0, 0, 5, 5))
        self.assertIsNone(GameOfLife(3, 3).bbox())

    def test_add_out_of_bounds_raises(self):
        with self.assertRaises(ValueError):
            GameOfLife(5, 5, [(5, 0)])
        g = GameOfLife(5, 5)
        with self.assertRaises(ValueError):
            g.add([(0, -1)])

    def test_wrap_torus_crosses_edges(self):
        # 环面上横跨左右边界的蜂鸣器 → 转成贴着边界的竖蜂鸣器
        g = GameOfLife(5, 5, [(4, 0), (0, 0), (1, 0)], wrap=True)
        g.step()
        self.assertEqual(g.live_cells, frozenset([(0, 4), (0, 0), (0, 1)]))
        # 同样的细胞在有限平面上会全部死掉
        flat = GameOfLife(5, 5, [(4, 0), (0, 0), (1, 0)])
        flat.step()
        self.assertEqual(flat.population, 0)

    def test_copy_is_independent(self):
        g = GameOfLife(8, 8, [(2, 2)])
        clone = g.copy()
        clone.step()
        self.assertEqual(g.population, 1)
        self.assertEqual(clone.population, 0)
        self.assertEqual(g.generation, 0)
        self.assertEqual(clone.generation, 1)


class TestBatch(unittest.TestCase):
    def test_run_steps_in_place(self):
        g = GameOfLife(6, 6, [(1, 1)])
        result = g.run(5)
        self.assertIs(result, g)
        self.assertEqual(g.generation, 5)

    def test_evolve_collects_frames(self):
        g = GameOfLife(6, 6, [(1, 1)])
        frames = g.evolve(3)
        self.assertEqual(len(frames), 4)  # 含初始代
        self.assertEqual(frames[0].generation, 0)
        self.assertEqual(frames[-1].generation, 3)
        self.assertIsNot(frames[0], g)

    def test_negative_steps_raise(self):
        g = GameOfLife(4, 4)
        with self.assertRaises(ValueError):
            g.run(-1)
        with self.assertRaises(ValueError):
            g.evolve(-1)


if __name__ == "__main__":
    unittest.main()
