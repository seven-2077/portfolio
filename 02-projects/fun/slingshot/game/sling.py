"""弹弓交互：拉伸瞄准（角度+力度）、皮筋约束、抛物线轨迹预测、发射。"""
from __future__ import annotations

import math

from physics import verlet
from game.world import World

MAX_STRETCH = 3.0  # 最大拉伸（世界单位）
K = 15.0  # 拉伸量 → 出膛速度 (单位/秒 每单位)
PREDICT_STEPS = 110  # 轨迹预演步数（≈0.9 秒）


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class Slingshot:
    """弹弓控制器。angle=仰角（度，0=水平向右，90=垂直向上），power=力度 0..1。"""

    def __init__(self, world: World):
        self.world = world

    # —— 瞄准 ——

    def pull(self, angle_deg: float, power: float) -> tuple[float, float]:
        """拉弓到位，返回出膛速度 (vx, vy)。y 轴向下，向上发射 vy 为负。"""
        power = clamp(power, 0.0, 1.0)
        stretch = power * MAX_STRETCH
        rad = math.radians(angle_deg)
        ux, uy = math.cos(rad), -math.sin(rad)  # 发射方向单位向量
        ax, ay = self.world.anchor
        if not self.world.projectile:
            self.world.spawn()
        self.world.hold_at(ax - ux * stretch, ay - uy * stretch)
        v = K * stretch
        return v * ux, v * uy

    def hold(self, angle_deg: float, power: float) -> None:
        """只拉弓不发射（渲染瞄准态用）。"""
        self.pull(angle_deg, power)

    # —— 轨迹预测 ——

    def predict(self, angle_deg: float, power: float) -> list[tuple[float, float]]:
        """用与实射完全相同的 Verlet 步进做抛物线预演（无碰撞）。"""
        vx, vy = self.pull(angle_deg, power)
        p = self.world.projectile
        if p is None:
            return []
        q = verlet.Particle(p.p.x, p.p.y, p.p.x, p.p.y, inv_mass=p.p.inv_mass)
        q.ax, q.ay = 0.0, self.world.gravity
        q.set_velocity(vx, vy, self.world.dt)
        out: list[tuple[float, float]] = []
        for _ in range(PREDICT_STEPS):
            verlet.step([q], self.world.dt)
            out.append((q.x, q.y))
            if q.y > self.world.ground_y - 0.05 or q.x > self.world.width + 2:
                break
        return out

    # —— 发射 ——

    def release(self, angle_deg: float, power: float) -> tuple[float, float]:
        """拉弓并松手发射，返回出膛速度。"""
        vx, vy = self.pull(angle_deg, power)
        self.world.release(vx, vy)
        return vx, vy

    # —— 交互输入 ——

    @staticmethod
    def prompt_aim(default_angle: float = 55.0, default_power: float = 80.0) -> tuple[float, float]:
        """键盘输入角度/力度（回车采用默认值）。"""
        raw = input(f" 角度 {default_angle:.0f}° (0-150): ").strip()
        angle = float(raw) if raw else default_angle
        raw = input(f" 力度 {default_power:.0f}% (1-100): ").strip()
        power = (float(raw) if raw else default_power) / 100.0
        return angle, clamp(power, 0.01, 1.0)
