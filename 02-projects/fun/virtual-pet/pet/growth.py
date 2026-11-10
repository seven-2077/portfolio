"""pet.growth — 四段成长：蛋 → 幼年 → 成年 → 老年。

只按年龄逐级晋升（只升不降）；健康不足会卡住成长——吃得饱睡得好才长得大。
每阶段自带状态阈值（hunger_danger 越老越敏感）与形象 key。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    key: str            # sprites 形象用的 key
    name: str           # 中文名（界面展示）
    min_age: float      # 晋升所需年龄（秒）
    hunger_danger: float    # 该阶段的饥饿警戒线（越高越抗饿）
    desc: str


STAGES: tuple[Stage, ...] = (
    Stage("egg", "蛋", 0.0, 95.0, "一颗会眨眼的蛋，饿得慢但碰不得病"),
    Stage("baby", "幼年", 60 * 60.0, 85.0, "毛茸茸的幼体，活泼但体质弱"),
    Stage("adult", "成年", 6 * 3600.0, 80.0, "壮年期，抗饿耐玩"),
    Stage("elder", "老年", 10 * 3600.0, 70.0, "老了，吃得少动得慢，需要多照看"),
)

GROW_MIN_HEALTH = 50          # 晋升所需的最低健康


def age_stage(age_seconds: float) -> int:
    """按年龄算「应该」在第几阶段（可能因健康不达标而暂时到不了）。"""
    idx = 0
    for i, stage in enumerate(STAGES):
        if age_seconds >= stage.min_age:
            idx = i
    return idx


def stage_at(index: int) -> Stage:
    """按序号取阶段（越界时夹到边界）。"""
    return STAGES[max(0, min(index, len(STAGES) - 1))]


def try_grow(current: int, age_seconds: float,
             health: float) -> tuple[int, str | None]:
    """尝试把阶段推进到年龄对应的档位。

    返回 (新阶段序号, 事件消息或 None)。健康不足时停滞不前（序号不变），
    阶段只升不降，因此不会因生病掉回「蛋」。
    """
    want = age_stage(age_seconds)
    if want <= current:
        return current, None
    if health < GROW_MIN_HEALTH:
        nxt = stage_at(current + 1)
        return current, (f"营养不足（健康 {round(health)}），"
                         f"迟迟长不成「{nxt.name}」……")
    target = min(want, current + 1)     # 每次只晋升一级，形象逐步变化
    old, new = stage_at(current), stage_at(target)
    return target, f"{old.name} → {new.name}！{pet_growth_line(new)}"


def pet_growth_line(stage: Stage) -> str:
    """阶段跨越时的宣传语。"""
    return {
        "egg": "壳裂开一道缝，里面有东西在动！",
        "baby": "破壳而出，毛茸茸的小家伙出现了！",
        "adult": "抽条长个，长成大人的样子了！",
        "elder": "胡子都白了，进入了颐养天年的阶段。",
    }[stage.key]
