"""pet.engine — 宠物状态、真实时间演化与状态机。

时间模型：只在 advance() 被调用时按时间戳增量结算，关机期间一次性补算——
离线单次最多按 MAX_OFFLINE_SECONDS 计，且间隔超过 OFFLINE_GRACE 打
OFFLINE_FACTOR 折扣。摆烂一周回来宠物会变差，但不会瞬间病危/老化。
状态机与转移图见 README「状态机设计」。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import NamedTuple

from . import growth

# ---------- 速率常数（属性点 / 秒） ----------

HUNGER_RATE = 100 / (8 * 3600)      # 在线 8 小时从饱食 → 饥饿爆表
MOOD_RATE = 100 / (10 * 3600)       # 10 小时无互动心情见底
ENERGY_DRAIN = 100 / (16 * 3600)    # 清醒 16 小时能量耗尽
ENERGY_SLEEP = 100 / (5 * 3600)     # 睡 5 小时回满
HEALTH_DECAY = 100 / (4 * 3600)     # 长期受苦 4 小时健康清零
HEALTH_HEAL = 100 / (4 * 3600)      # 吃饱睡好 4 小时回满

# ---------- 阈值与规则 ----------

ENERGY_ZERO = 0.0
STRESS_SECONDS = 3600       # 连续饥饿/耗能多久才算「长期」（1h）
SICK_AT = 30                # 健康低于此值 → sick
RECOVER_AT = 45             # sick 状态回到 idle 的健康线

FEED_FILL = 35.0            # 一次喂食的饱食增量（再乘 1+bonus）
FEED_MOOD = 5.0
PLAY_MOOD = 20.0            # 玩耍的心情增量
PLAY_ENERGY = 15.0          # 玩耍的能量开销
PLAY_MIN_ENERGY = 15.0      # 玩耍的入场能量
PLAY_MIN_HEALTH = SICK_AT   # 生病时不能玩

EATING_SECONDS = 10.0       # 吃饭动画时长（结算时间）
PLAYING_SECONDS = 15.0      # 玩耍动画时长
SLEEP_MAX_SECONDS = 10 * 3600   # 一觉最多睡 10 小时

MAX_OFFLINE_SECONDS = 12 * 3600  # 离线最多补算 12 小时
OFFLINE_GRACE = 120              # 超过 2 分钟的间隔视为离线
OFFLINE_FACTOR = 0.5             # 离线结算量打对折

# 状态名（对外展示用中文，在 interact 里映射）
IDLE, EATING, PLAYING, SLEEPING, SICK = "idle", "eating", "playing", "sleeping", "sick"


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """把属性值限制在 [lo, hi]。"""
    return max(lo, min(hi, value))


@dataclass
class PetState:
    """宠物的全部可持久化状态。属性一律 0-100，hunger 越大越饿。"""

    name: str = "小煤球"
    hunger: float = 30.0     # 0 = 饱，100 = 快饿晕
    mood: float = 70.0
    energy: float = 80.0
    health: float = 90.0
    age_seconds: float = 0.0
    stage_idx: int = 0       # 成长阶段（只升不降，详见 growth）
    status: str = IDLE
    action_left: float = 0.0     # eating/playing 的剩余时长
    sleep_left: float = 0.0      # sleeping 的剩余时长
    stress_seconds: float = 0.0  # 连续饥饿/耗能累计
    grow_warned: bool = False    # 「营养不足」是否已警告过（防重复刷屏）
    sick_noted: bool = False     # 本次病程是否已播报过「生病了」
    last_tick: float = 0.0       # 上次结算的时间戳
    born_at: float = 0.0


class Action(NamedTuple):
    """一次玩家动作的结果：ok + 展示消息。"""

    ok: bool
    message: str


def new_pet(name: str = "小煤球", now: float | None = None) -> PetState:
    """创建一只新宠物，时间戳锚定到当下。"""
    now = time.time() if now is None else now
    return PetState(name=name, last_tick=now, born_at=now)


def _stage_danger(pet: PetState) -> float:
    """当前阶段的饥饿警戒线（各阶段不同，越老越容易出事）。"""
    return growth.stage_at(pet.stage_idx).hunger_danger


def _advance_clock(pet: PetState, now: float) -> float:
    """推进时间戳，返回本次生效的结算秒数（已含离线上限与折扣）。"""
    if pet.last_tick <= 0:
        pet.last_tick = now
        return 0.0
    raw = now - pet.last_tick
    pet.last_tick = now
    if raw <= 0:                # 时钟回拨：不结算，只对齐
        return 0.0
    eff = min(raw, MAX_OFFLINE_SECONDS)
    if raw > OFFLINE_GRACE:     # 离线：衰减折扣
        eff *= OFFLINE_FACTOR
    return eff


def advance(pet: PetState, now: float | None = None) -> list[str]:
    """按真实时间增量结算一次演化，返回事件日志（可能为空）。"""
    now = time.time() if now is None else now
    eff = _advance_clock(pet, now)
    if eff <= 0:
        return []
    events: list[str] = []

    # 年龄 + 基础属性随时间变化
    pet.age_seconds += eff
    pet.hunger = clamp(pet.hunger + HUNGER_RATE * eff)
    sick_mood_drag = 1.3 if pet.status == SICK else 1.0
    pet.mood = clamp(pet.mood - MOOD_RATE * eff * sick_mood_drag)

    # 能量：睡觉恢复，醒着消耗
    if pet.status == SLEEPING:
        pet.energy = clamp(pet.energy + ENERGY_SLEEP * eff)
        pet.sleep_left -= eff
    else:
        pet.energy = clamp(pet.energy - ENERGY_DRAIN * eff)

    # 短状态（吃饭/玩耍）计时结束：病没好就回到 sick，不重复播报
    if pet.action_left > 0:
        pet.action_left -= eff
        if pet.action_left <= 0:
            pet.action_left = 0.0
            if pet.status == EATING:
                events.append(f"{pet.name} 吃完最后一口，心满意足。")
            elif pet.status == PLAYING:
                events.append(f"{pet.name} 玩够了，趴下来歇气。")
            pet.status = SICK if pet.health <= SICK_AT else IDLE

    # 压力累积（饥饿到警戒线，或能量耗尽），封顶 2 倍阈值防止爆表
    danger = _stage_danger(pet)
    overwhelmed = pet.hunger >= danger or pet.energy <= ENERGY_ZERO
    if overwhelmed:
        pet.stress_seconds = min(pet.stress_seconds + eff,
                                 2 * STRESS_SECONDS)
    else:
        pet.stress_seconds = max(0.0, pet.stress_seconds - eff)

    # 健康：长期受苦则掉，吃饱睡好（压力清了）则回升
    if pet.stress_seconds >= STRESS_SECONDS:
        pet.health = clamp(pet.health - HEALTH_DECAY * eff)
    elif pet.hunger <= 60 and pet.energy >= 15:
        pet.health = clamp(pet.health + HEALTH_HEAL * eff)

    # 睡眠自然结束
    if pet.status == SLEEPING and (pet.energy >= 100 or pet.sleep_left <= 0):
        pet.status = SICK if pet.health <= SICK_AT else IDLE
        events.append(f"{pet.name} 伸了个懒腰醒来了。")

    # 成长阶段判定（健康不足会停滞，但绝不降级）
    new_idx, grow_msg = growth.try_grow(
        pet.stage_idx, pet.age_seconds, pet.health)
    if new_idx != pet.stage_idx:
        pet.stage_idx = new_idx
        pet.grow_warned = False
        events.append(grow_msg)
    elif grow_msg and not pet.grow_warned:
        pet.grow_warned = True     # 营养不足只警告一次
        events.append(grow_msg)

    # 状态机转移
    events.extend(_transition(pet))
    return events


def _transition(pet: PetState) -> list[str]:
    """状态机转移：生病每场只播报一次（sick_noted），康复时复位。"""
    if pet.status in (EATING, PLAYING, SLEEPING):
        return []                       # 动作状态有自己的退出规则
    if pet.health <= SICK_AT:
        pet.status = SICK
        if not pet.sick_noted:
            pet.sick_noted = True
            return [f"{pet.name} 生病了，需要好好喂养休息……"]
        return []
    if pet.status == SICK and pet.health >= RECOVER_AT:
        pet.status = IDLE
        pet.sick_noted = False
        return [f"{pet.name} 康复了，又活蹦乱跳！"]
    return []


# ---------- 玩家动作（状态机输入） ----------

def feed(pet: PetState, bonus: float = 0.0) -> Action:
    """喂食：饱食上升；bonus 为 studylink 学习加成（0~0.5 可叠加）。"""
    if pet.status == SLEEPING:
        return Action(False, "它睡得正香，先把它叫醒吧。")
    fill = FEED_FILL * (1 + bonus)
    pet.hunger = clamp(pet.hunger - fill)
    pet.mood = clamp(pet.mood + FEED_MOOD + FEED_MOOD * bonus)
    pet.stress_seconds = max(0.0, pet.stress_seconds - STRESS_SECONDS)
    pet.status = EATING
    pet.action_left = EATING_SECONDS
    pct = f"+{round(bonus * 100)}%" if bonus else "无"
    return Action(True, f"{pet.name} 啊呜啊呜吃起来了（饱食 +{round(fill)}"
                        f"，学习加成 {pct}）")


def play(pet: PetState, bonus: float = 0.0) -> Action:
    """玩耍：心情↑、能量↓；生病或太累时被拒绝（守卫条件）。"""
    if pet.status == SLEEPING:
        return Action(False, "嘘——它在睡觉，别吵醒它。")
    if pet.status == SICK or pet.health <= PLAY_MIN_HEALTH:
        return Action(False, f"{pet.name} 病着呢，先喂食休息吧。")
    if pet.energy < PLAY_MIN_ENERGY:
        return Action(False, f"{pet.name} 太累了，先睡一觉恢复能量。")
    pet.mood = clamp(pet.mood + PLAY_MOOD * (1 + bonus * 0.6))
    pet.energy = clamp(pet.energy - PLAY_ENERGY)
    pet.hunger = clamp(pet.hunger + 5)
    pet.status = PLAYING
    pet.action_left = PLAYING_SECONDS
    return Action(True, f"{pet.name} 玩得咯咯直乐（心情↑ 能量↓）")


def sleep(pet: PetState) -> Action:
    """睡觉：进入 sleeping，能量随时间恢复。"""
    if pet.status == SLEEPING:
        return Action(False, "它已经睡着了。")
    if pet.status == EATING:
        return Action(False, "它正在吃饭，让它吃完再说。")
    pet.status = SLEEPING
    pet.action_left = 0.0
    pet.sleep_left = SLEEP_MAX_SECONDS
    return Action(True, f"{pet.name} 蜷成一团睡着了 zZ……")


def wake(pet: PetState) -> Action:
    """手动叫醒。"""
    if pet.status != SLEEPING:
        return Action(False, "它本来就醒着。")
    pet.status = SICK if pet.health <= SICK_AT else IDLE
    pet.sleep_left = 0.0
    return Action(True, f"{pet.name} 揉揉眼睛醒了过来。")
