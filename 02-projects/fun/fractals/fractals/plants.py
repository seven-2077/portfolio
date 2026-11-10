"""预置 L-system 植物 / 曲线。

每个预置是一份「遗传信息」：公理 + 规则表 + 推荐角度 + 推荐迭代数。
核心卖点在这里体现——一棵分形树的全部遗传信息只有三行规则。

命名说明：蕨类采用经典 bush / fern 形态（X 辅助符 + F 笔画的
「算法之美」配方），另附一个带随机规则可选位的 bush 变体，
展示同一段遗传信息如何长出略有差异的个体。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lsystem import LSystem, RuleValue

__all__ = ["Plant", "PRESETS", "make_lsystem"]


@dataclass(frozen=True)
class Plant:
    """一份 L-system「遗传信息」。"""

    name: str
    axiom: str
    rules: dict[str, RuleValue] = field(default_factory=dict)
    angle: float = 90.0
    iterations: int = 4
    stochastic: bool = False
    description: str = ""

    def lsystem(self, seed: int | None = None) -> LSystem:
        return LSystem(self.axiom, self.rules,
                       stochastic=self.stochastic, seed=seed)


def make_lsystem(plant: Plant, seed: int | None = None) -> LSystem:
    """从预置植物构造可迭代的 L-system 实例。"""
    return plant.lsystem(seed=seed)


# ----------------------------------------------------------------------
# 预置表
# ----------------------------------------------------------------------

PRESETS: dict[str, Plant] = {}


def _register(plant: Plant) -> Plant:
    PRESETS[plant.name] = plant
    return plant


_register(Plant(
    name="fern",
    axiom="X",
    rules={
        "X": "F+[[X]-X]-F[-FX]+X",
        "F": "FF",
    },
    angle=25.0,
    iterations=4,
    description="蕨类（经典 fern/bush 配方）：X 负责分枝拓扑，F 负责茎干伸长。",
))

_register(Plant(
    name="tree",
    axiom="F",
    rules={"F": "F[+F]F[-F]F"},
    angle=25.0,
    iterations=4,
    description="分形树：一行规则递归出主干、分枝与细梢。",
))

_register(Plant(
    name="koch_snowflake",
    axiom="F--F--F",
    rules={"F": "F+F--F+F"},
    angle=60.0,
    iterations=4,
    description="Koch 雪花：等边三角形三条边各自生长出 60° 锯齿。",
))

_register(Plant(
    name="koch_curve",
    axiom="F",
    rules={"F": "F+F--F+F"},
    angle=60.0,
    iterations=4,
    description="Koch 曲线（单边）：长度按 (4/3)^n 发散，维数 log4/log3 ≈ 1.262。",
))

_register(Plant(
    name="dragon",
    axiom="FX",
    rules={
        "X": "X+YF+",
        "Y": "-FX-Y",
    },
    angle=90.0,
    iterations=12,
    description="龙曲线：X/Y 只管折纸拓扑，F 是最终留下的笔迹。",
))

_register(Plant(
    name="bush_random",
    axiom="F",
    rules={
        "F": ("F[+F]F[-F]F", "F[+F]F", "F[-F]F"),
    },
    angle=22.5,
    iterations=4,
    stochastic=True,
    description="随机灌木：三条候选规则等概率抽取，同一种子长同一棵，换种换一棵。",
))
