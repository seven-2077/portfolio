"""L-system 重写引擎测试：精确展开断言 + 输入校验 + 随机模式。"""
import unittest

from fractals.lsystem import LSystem


class TestDeterministicRewrite(unittest.TestCase):
    def test_n_zero_returns_axiom(self):
        ls = LSystem("A", {"A": "AB"})
        self.assertEqual(ls.iterate(0), "A")

    def test_fibonacci_words_exact(self):
        """Fibonacci 词：A→AB、B→A 的前 5 代必须逐字精确。"""
        ls = LSystem("A", {"A": "AB", "B": "A"})
        expected = ["A", "AB", "ABA", "ABAAB", "ABAABABA"]
        for n, want in enumerate(expected):
            self.assertEqual(ls.iterate(n), want, f"n={n}")

    def test_fern_first_iteration_exact(self):
        """蕨类公理 X 的第 1 代就是规则右部本身（并行重写一步到位）。"""
        ls = LSystem("X", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"})
        self.assertEqual(ls.iterate(1), "F+[[X]-X]-F[-FX]+X")

    def test_unknown_symbols_preserved(self):
        """无规则的符号（X、Y 等辅助符）原样保留。"""
        self.assertEqual(LSystem("X", {"F": "FF"}).iterate(2), "X")
        self.assertEqual(LSystem("FXY", {"F": "FF"}).iterate(1), "FFXY")

    def test_expand_is_alias_of_iterate(self):
        ls = LSystem("A", {"A": "AA"})
        self.assertEqual(ls.expand(3), ls.iterate(3))

    def test_parallel_rewrite_applies_to_all_symbols(self):
        """并行性：同一代里每个 F 都被替换，而不是逐个串行推导。"""
        ls = LSystem("FF", {"F": "F+F"})
        # 2 个 F 同代各自展开 → "F+F"+"F+F" 相邻拼接出中间的 FF
        self.assertEqual(ls.iterate(1), "F+FF+F")
        self.assertEqual(ls.iterate(2), "F+F+F+FF+F+F+F")


class TestValidation(unittest.TestCase):
    def test_empty_axiom_raises(self):
        with self.assertRaises(ValueError):
            LSystem("", {"A": "B"})

    def test_empty_symbol_key_raises(self):
        with self.assertRaises(ValueError):
            LSystem("A", {"": "A"})

    def test_empty_production_raises(self):
        with self.assertRaises(ValueError):
            LSystem("A", {"A": ""})

    def test_multi_candidate_requires_stochastic(self):
        with self.assertRaises(ValueError):
            LSystem("A", {"A": ("AA", "B")})
        # 显式开启随机模式则合法
        LSystem("A", {"A": ("AA", "B")}, stochastic=True)

    def test_negative_iterations_raise(self):
        with self.assertRaises(ValueError):
            LSystem("A", {"A": "A"}).iterate(-1)


class TestStochastic(unittest.TestCase):
    RULES = {"F": ("F[+F]F", "F[+F]F", "F[-F]F")}

    def test_same_seed_reproducible(self):
        a = LSystem("F", self.RULES, stochastic=True, seed=7).iterate(4)
        b = LSystem("F", self.RULES, stochastic=True, seed=7).iterate(4)
        self.assertEqual(a, b)

    def test_different_seed_differs(self):
        a = LSystem("F", self.RULES, stochastic=True, seed=7).iterate(4)
        c = LSystem("F", self.RULES, stochastic=True, seed=8).iterate(4)
        self.assertNotEqual(a, c)

    def test_stochastic_symbols_stay_in_alphabet(self):
        code = LSystem("F", self.RULES, stochastic=True, seed=1).iterate(4)
        for ch in code:
            self.assertIn(ch, "F[]+-")


class TestMetadata(unittest.TestCase):
    def test_describe_and_size(self):
        ls = LSystem("F", {"F": "FF", "X": "X+X"})
        self.assertEqual(ls.size, 2)
        desc = ls.describe()
        self.assertIn("公理: F", desc)
        self.assertIn("F → FF", desc)
        self.assertIn("X → X+X", desc)

    def test_repr_mentions_mode(self):
        self.assertIn("deterministic", repr(LSystem("A", {"A": "A"})))
        self.assertIn("stochastic",
                      repr(LSystem("A", {"A": ("A", "B")}, stochastic=True)))


if __name__ == "__main__":
    unittest.main()
