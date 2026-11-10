"""战斗：准星 hitscan 命中判定、伤害与生死、拾取物、胜负判定。

射击不是「发射一颗慢慢飞的子弹」，而是**沿准星方向瞬间打一条射线**
（hitscan）：先算这发子弹能飞多远（撞墙距离），再看哪些敌人的**角半径**
罩进了准星 —— 敌人越近看起来越大，`atan(半径/距离)` 就是它在你眼里张开
的角度；张角 + 容差内最近的那个吃伤害。隔墙的敌人角半径再大也不算，
因为射线被墙截断了。
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .raycaster import MAX_DEPTH, cast_ray
from .sprites import ENEMY_SPEC, PICKUP_VALUE

__all__ = ["try_shoot", "damage_player", "collect_pickups", "check_exit",
           "check_end", "WEAPON_DAMAGE", "AIM_TOLERANCE", "EXIT_BONUS_SCORE"]

WEAPON_DAMAGE = 34        # 一枪 34：哨兵 2 枪、猎杀者 3 枪
AIM_TOLERANCE = 0.03      # 额外瞄准容差（弧度）
EXIT_BONUS_SCORE = 50


def angle_delta(a: float, b: float) -> float:
    """a − b，折回 (−π, π]，用于比较两条射线的夹角。"""
    return (a - b + math.pi) % math.tau - math.pi


def try_shoot(game) -> Tuple[str, Optional[object]]:
    """开一枪。返回 ("hit"/"kill"/"miss"/"no_ammo", 目标或 None)。"""
    player = game.player
    if player.ammo <= 0:
        game.push("弹药耗尽——去找绿色的弹药箱")
        return "no_ammo", None
    player.ammo -= 1
    wall = cast_ray(game.gmap, player.x, player.y, player.angle)
    wall_dist = wall.dist if wall.hit else MAX_DEPTH
    # 枪声把附近的敌人惊动（即使隔着墙也会开始找路）
    for enemy in game.enemies:
        if enemy.alive and math.hypot(enemy.x - player.x,
                                      enemy.y - player.y) <= 9.0:
            enemy.aggro = max(enemy.aggro, 5.0)
    best, best_dist = None, math.inf
    for enemy in game.enemies:
        if not enemy.alive:
            continue
        rel_x, rel_y = enemy.x - player.x, enemy.y - player.y
        dist = math.hypot(rel_x, rel_y)
        if dist > wall_dist + 0.25:           # 隔着墙，打不着
            continue
        aim = math.atan2(ENEMY_SPEC[enemy.kind]["radius"], max(dist, 1e-6))  # type: ignore[arg-type]
        if abs(angle_delta(math.atan2(rel_y, rel_x), player.angle)) \
                <= aim + AIM_TOLERANCE and dist < best_dist:
            best, best_dist = enemy, dist
    if best is None:
        game.push("未命中")
        return "miss", None
    died = best.hurt(WEAPON_DAMAGE)
    if died:
        player.score += best.score_value
        game.push(f"{best.name}被消灭  +{best.score_value}")
        return "kill", best
    game.push(f"命中 {best.name}（剩 {best.hp} HP）")
    return "hit", best


def damage_player(game, amount: int) -> None:
    """敌人近战结算：扣血、飘提示、血量归零触发失败。"""
    player = game.player
    player.take_damage(amount)
    if not player.alive:
        game.push("你倒下了……")
    else:
        game.push(f"被攻击 −{amount}（HP {player.hp}）")


def collect_pickups(game) -> List[str]:
    """走近拾取物：弹药 +12 / 医疗 +30，附带得分。"""
    player = game.player
    messages: List[str] = []
    for pickup in game.pickups:
        if pickup.taken:
            continue
        if math.hypot(pickup.x - player.x, pickup.y - player.y) > 0.55:
            continue
        pickup.taken = True
        value = PICKUP_VALUE[pickup.kind]
        if pickup.kind == "ammo":
            player.ammo += value
            messages.append(f"拾取弹药 +{value}")
        else:
            player.hp = min(100, player.hp + value)
            messages.append(f"医疗包 +{value}（HP {player.hp}）")
        player.score += 10
    return messages


def check_exit(game) -> Optional[str]:
    """第一次踏上出口的额外奖励（清敌通关本身不依赖出口）。"""
    if game.exit_taken:
        return None
    player = game.player
    if not game.gmap.is_exit(player.x, player.y):
        return None
    game.exit_taken = True
    player.score += EXIT_BONUS_SCORE
    return f"抵达出口  +{EXIT_BONUS_SCORE}"


def check_end(game) -> Optional[str]:
    """胜负：血量归零 = 失败；场上敌人清空 = 通关。"""
    if not game.player.alive or game.player.hp <= 0:
        return "lose"
    if game.enemies and all(not e.alive for e in game.enemies):
        return "win"
    return None
