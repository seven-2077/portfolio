"""得分规则：结构破坏量 + 剩余弹丸奖励。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# 各材质基准分：玻璃脆好拆但分低，石块难拆分高
POINTS = {"wood": 100, "glass": 60, "stone": 150}
AMMO_BONUS = 400  # 每发剩余弹丸
CLEAR_BONUS = 500  # 全拆完额外奖励


@dataclass
class Score:
    destruction: int  # 破坏得分
    ammo_bonus: int
    clear_bonus: int
    total: int
    broken: int
    total_blocks: int
    rate: float  # 0..1 破坏率
    by_material: dict[str, int]


def evaluate(
    broken_counts: dict[str, int] | Counter,
    total_blocks: int,
    ammo_left: int,
) -> Score:
    counts = Counter(broken_counts)
    destruction = sum(POINTS[m] * n for m, n in counts.items())
    broken = sum(counts.values())
    rate = broken / total_blocks if total_blocks else 0.0
    clear = CLEAR_BONUS if total_blocks and broken >= total_blocks else 0
    ammo_bonus = AMMO_BONUS * max(0, ammo_left)
    return Score(
        destruction=destruction,
        ammo_bonus=ammo_bonus,
        clear_bonus=clear,
        total=destruction + ammo_bonus + clear,
        broken=broken,
        total_blocks=total_blocks,
        rate=rate,
        by_material=dict(counts),
    )
