"""Verlet 积分器：位置更新 + 距离约束的迭代松弛。

核心思想：不显式维护速度，速度隐含在「当前坐标 - 上一步坐标」里。
这让位置约束（皮筋、绳、杆）变得极好写——直接挪坐标即可，
速度会自动被"带过去"，天然满足约束求解后的动量守恒近似。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Particle:
    """一个参与 Verlet 积分的质点。"""

    x: float
    y: float
    px: float  # 上一步位置（velocity = (x - px) / dt）
    py: float
    inv_mass: float = 1.0
    ax: float = 0.0  # 外力加速度（含重力）
    ay: float = 0.0
    fixed: bool = False  # 锚点：不积分
    sleeping: bool = False  # 休眠：冻结积分，防堆叠抖动
    sleep_timer: float = 0.0

    def velocity(self, dt: float) -> tuple[float, float]:
        return (self.x - self.px) / dt, (self.y - self.py) / dt

    def speed(self, dt: float) -> float:
        vx, vy = self.velocity(dt)
        return math.hypot(vx, vy)

    def set_velocity(self, vx: float, vy: float, dt: float) -> None:
        """反推 px/py，让下一步的隐含速度等于 (vx, vy)。"""
        self.px = self.x - vx * dt
        self.py = self.y - vy * dt

    def apply_velocity(self, dvx: float, dvy: float, dt: float) -> None:
        """施加速度增量（冲量 / m），只挪 prev 不挪 pos。"""
        self.px -= dvx * dt
        self.py -= dvy * dt

    def translate(self, dx: float, dy: float) -> None:
        """纯平移：同时挪 pos 和 prev，不产生速度。"""
        self.x += dx
        self.px += dx
        self.y += dy
        self.py += dy

    def wake(self) -> None:
        self.sleeping = False
        self.sleep_timer = 0.0

    def sleep(self) -> None:
        self.sleeping = True
        self.px, self.py = self.x, self.y


def step(particles: list[Particle], dt: float, damping: float = 0.9996) -> None:
    """一步位置 Verlet：x += v*damping + a*dt²。"""
    dt2 = dt * dt
    for p in particles:
        if p.fixed or p.sleeping:
            continue
        vx = (p.x - p.px) * damping
        vy = (p.y - p.py) * damping
        p.px, p.py = p.x, p.y
        p.x += vx + p.ax * dt2
        p.y += vy + p.ay * dt2


@dataclass
class DistanceConstraint:
    """距离约束：两质点间距收敛到 rest。

    弹弓皮筋 = 锚点(固定) ↔ 弹丸(动态) 的两条约束；
    绳 = 链式约束；杆 = 同一公式加 stiffness=1。
    """

    a: Particle
    b: Particle
    rest: float
    stiffness: float = 1.0
    one_sided: bool = False  # True = 只限制拉长（橡皮筋），松弛不推

    def solve(self) -> float:
        """松弛一次，返回修正后的长度误差（供测试观测收敛）。"""
        dx = self.b.x - self.a.x
        dy = self.b.y - self.a.y
        dist = math.hypot(dx, dy)
        w = self.a.inv_mass + self.b.inv_mass
        if dist < 1e-12 or w <= 0.0:
            return dist - self.rest if dist else 0.0
        if self.one_sided and dist <= self.rest:
            return 0.0  # 松弛态：皮筋不发力
        wa, wb = self.a.inv_mass / w, self.b.inv_mass / w
        diff = (dist - self.rest) / dist * self.stiffness
        self.a.x += dx * diff * wa
        self.a.y += dy * diff * wa
        self.b.x -= dx * diff * wb
        self.b.y -= dy * diff * wb
        # 修正 pos 后同步 prev，避免产生虚假速度
        self.a.px += dx * diff * wa
        self.a.py += dy * diff * wa
        self.b.px -= dx * diff * wb
        self.b.py -= dy * diff * wb
        return (dist - self.rest) * (1.0 - self.stiffness)


class Rope:
    """绳/杆：一串质点 + 相邻距离约束（弹弓皮筋即两条独立约束）。"""

    def __init__(self, points: list[Particle], segment: float, stiffness: float = 1.0):
        self.points = points
        self.links = [
            DistanceConstraint(points[i], points[i + 1], segment, stiffness)
            for i in range(len(points) - 1)
        ]

    def solve(self, iterations: int) -> float:
        """迭代松弛，返回最大长度误差。"""
        err = 0.0
        for _ in range(iterations):
            for link in self.links:
                link.solve()
        for link in self.links:
            d = math.hypot(link.b.x - link.a.x, link.b.y - link.a.y)
            err = max(err, abs(d - link.rest))
        return err

