"""结构：三种材质 + 耐久阈值碎裂 + 连锁唤醒 + 休眠防抖。

损伤模型：单次碰撞冲量 j 记入 hp，hp 归零 → 碎裂移除 →
唤醒邻居（连锁），并生成碎块（debris）粒子。
低于 MIN_IMPULSE 的微接触不计损伤，避免静置磨损。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .collision import Box
from .verlet import Particle

MIN_IMPULSE = 1.0  # 低于此冲量不计损伤


@dataclass(frozen=True)
class Material:
    name: str
    density: float  # 面密度 → 质量 = density * 面积
    durability: float  # 耐久阈值：累计冲量超过即碎
    char: str  # 终端字符画
    color: str  # SVG 填充色
    opacity: float
    debris: int  # 碎裂产生的碎块数


MATERIALS: dict[str, Material] = {
    "wood": Material("wood", 1.0, 26.0, "▒", "#b07b46", 0.95, 4),
    "glass": Material("glass", 0.55, 8.0, "░", "#a8dcf0", 0.65, 6),
    "stone": Material("stone", 1.8, 34.0, "█", "#8d9299", 1.0, 5),
}


class Block(Box):
    """结构方块：AABB + 材质 + 生命值（耐久余量）。"""

    def __init__(self, x: float, y: float, w: float, h: float, material: str):
        m = MATERIALS[material]
        p = Particle(x, y, x, y, inv_mass=1.0 / (m.density * w * h))
        super().__init__(p, w / 2.0, h / 2.0, tag=material)
        self.material = m
        self.w, self.h = w, h
        self.hp = m.durability
        self.alive = True

    @property
    def name(self) -> str:
        return self.material.name

    def impact(self, impulse: float) -> bool:
        """施加冲量，超过耐久则碎裂。返回是否已碎。"""
        if not self.alive or impulse < MIN_IMPULSE:
            return False
        self.hp -= impulse
        if self.hp <= 0.0:
            self.alive = False
            return True
        return False


def make_debris(x: float, y: float, material: str, rng: random.Random) -> list[Particle]:
    """碎块：碎裂处溅出的小粒子（也走 Verlet，落地减速）。"""
    m = MATERIALS[material]
    out: list[Particle] = []
    for _ in range(m.debris):
        px = x + rng.uniform(-0.3, 0.3)
        py = y + rng.uniform(-0.3, 0.3)
        out.append(Particle(px, py, px, py, inv_mass=3.0))
    return out


class Dormancy:
    """休眠判定：速度低于阈值持续一定步数即冻结，防堆叠抖动。"""

    VEL_LIMIT = 0.45  # 单位/秒
    STEPS = 40  # 持续安静步数

    @staticmethod
    def update(particles: list[Particle], dt: float) -> int:
        asleep = 0
        for p in particles:
            if p.fixed or p.sleeping:
                asleep += 1
                continue
            if p.speed(dt) < Dormancy.VEL_LIMIT:
                p.sleep_timer += dt
                if p.sleep_timer >= Dormancy.STEPS * dt:
                    p.sleep()
                    asleep += 1
            else:
                p.sleep_timer = 0.0
        return asleep
