"""L-system 字符串重写引擎。

L-system（Lindenmayer system）由生物学家 Aristid Lindenmayer 于 1968 年提出，
最初用于描述丝状藻类的细胞分裂序列，核心思想是「并行重写」：
每一步迭代中，字符串里的每个符号同时被替换成一条产生式规则的右部。

与普通文法的串行推导不同，并行性正是它能刻画植物分支结构的原因——
同一时刻，主干和所有侧芽一起生长。

本模块只做字符串重写，不含任何几何语义；几何解释交给 turtle 模块。
"""
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Union

__all__ = ["LSystem", "RuleValue"]

# 一条规则的取值：单条字符串，或多条候选（随机模式下等概率抽取）
RuleValue = Union[str, Sequence[str]]


class LSystem:
    """公理 + 规则表 → 迭代 n 次的字符串。

    Parameters
    ----------
    axiom:
        初始字符串（第 0 代）。
    rules:
        符号 → 产生式。值为 str 表示确定性规则；值为 str 序列表示
        多个可选产生式，此时必须 ``stochastic=True``（随机规则可选位）。
    stochastic:
        为 True 时，多候选规则按均匀分布随机抽取；单候选规则不受影响，
        仍为确定性展开。
    seed:
        随机种子，便于复现同一棵「随机植物」。
    """

    def __init__(
        self,
        axiom: str,
        rules: Mapping[str, RuleValue],
        *,
        stochastic: bool = False,
        seed: int | None = None,
    ) -> None:
        if not axiom:
            raise ValueError("axiom 不能为空")
        normalized: dict[str, tuple[str, ...]] = {}
        for symbol, value in rules.items():
            if not symbol:
                raise ValueError("规则左部不能是空符号")
            alternatives = (value,) if isinstance(value, str) else tuple(value)
            if not alternatives or any(not alt for alt in alternatives):
                raise ValueError(f"符号 {symbol!r} 的产生式不能含空串")
            if len(alternatives) > 1 and not stochastic:
                raise ValueError(
                    f"符号 {symbol!r} 有 {len(alternatives)} 条候选规则，"
                    "请设置 stochastic=True 或只保留一条"
                )
            normalized[symbol] = alternatives
        self.axiom = axiom
        self.rules = normalized
        self.stochastic = stochastic
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    def step(self, code: str) -> str:
        """对整条字符串做一次并行重写；无规则的符号原样保留（如 X、Y 辅助符）。"""
        out: list[str] = []
        for ch in code:
            alternatives = self.rules.get(ch)
            if alternatives is None:
                out.append(ch)
            elif len(alternatives) == 1:
                out.append(alternatives[0])
            else:
                out.append(self._rng.choice(alternatives))
        return "".join(out)

    def iterate(self, n: int) -> str:
        """迭代 n 次（n=0 返回公理本身）。"""
        if n < 0:
            raise ValueError("迭代次数不能为负")
        code = self.axiom
        for _ in range(n):
            code = self.step(code)
        return code

    # 常用别名
    expand = iterate

    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        """规则表规模（可重写符号数）。"""
        return len(self.rules)

    def describe(self) -> str:
        """人类可读的规则表摘要，用于 README / demo 打印。"""
        lines = [f"公理: {self.axiom}"]
        for symbol, alternatives in self.rules.items():
            right = " | ".join(alternatives)
            lines.append(f"  {symbol} → {right}")
        return "\n".join(lines)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        mode = "stochastic" if self.stochastic else "deterministic"
        return f"LSystem(axiom={self.axiom!r}, rules={len(self.rules)}, {mode})"
