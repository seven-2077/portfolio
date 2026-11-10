"""世界编排：固定步长物理主循环（积分 → 松弛求解 → 碎裂 → 休眠）。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from physics import collision as col
from physics import verlet
from physics.structure import Block, Dormancy, make_debris

DT = 1.0 / 120.0  # 固定物理步长
COLLISION_ITERS = 6  # 每步碰撞松弛迭代次数
WAKE_DEPTH = 0.02  # 穿透超过此值唤醒休眠体
WAKE_J = 0.8  # 冲量超过此值唤醒休眠体
PROJ_R = 0.55
PROJ_MASS = 2.2
STOP_SPEED = 1.5  # 弹丸低速持续判定
STOP_TIME = 0.45


@dataclass
class BreakEvent:
    material: str
    x: float
    y: float


class World:
    """一局游戏的物理世界：方块 + 弹丸 + 碎块 + 地面。"""

    def __init__(self, spec, seed: int = 0):
        self.spec = spec
        self.width = spec.world_w
        self.height = spec.world_h
        self.ground_y = spec.ground_y
        self.gravity = spec.gravity
        self.dt = DT
        self.blocks = [
            Block(b.x, b.y, b.w, b.h, b.material) for b in spec.blocks
        ]
        for b in self.blocks:
            b.p.ay = self.gravity
        self.total_blocks = len(self.blocks)
        self.debris: list[tuple[verlet.Particle, str]] = []
        self.projectile: col.Circle | None = None
        self.holding = False
        self.bands: list[verlet.DistanceConstraint] = []
        self.events: list[BreakEvent] = []
        self.trail: list[tuple[float, float]] = []
        self.shot_active = False
        self.shot_steps = 0
        self.ammo_total = spec.ammo
        self.ammo_spent = 0
        self._stop_timer = 0.0
        self._dead: list[Block] = []
        self.rng = random.Random(seed)
        self.anchor = spec.sling
        tip_l = verlet.Particle(spec.sling[0] - 0.8, spec.sling[1] - 0.15, 0, 0, 0.0)
        tip_r = verlet.Particle(spec.sling[0] + 0.8, spec.sling[1] - 0.15, 0, 0, 0.0)
        self.tips = (tip_l, tip_r)

    # —— 弹丸生命周期 ——

    def spawn(self) -> bool:
        """在弹弓处生成弹丸并挂上皮筋（约束点）。"""
        if self.shot_active or self.ammo_spent >= self.ammo_total:
            return False
        x, y = self.anchor
        p = verlet.Particle(x, y, x, y, inv_mass=1.0 / PROJ_MASS)
        p.ay = self.gravity
        self.projectile = col.Circle(p, PROJ_R)
        self.ammo_spent += 1
        self.holding = True
        rest = (
            (self.anchor[0] - self.tips[0].x) ** 2
            + (self.anchor[1] - self.tips[0].y) ** 2
        ) ** 0.5 + 3.0
        self.bands = [
            verlet.DistanceConstraint(self.tips[0], p, rest, one_sided=True),
            verlet.DistanceConstraint(self.tips[1], p, rest, one_sided=True),
        ]
        return True

    def hold_at(self, x: float, y: float) -> None:
        """瞄准：把弹丸放到指定位置，皮筋约束就地松弛。"""
        if not (self.projectile and self.holding):
            return
        p = self.projectile.p
        p.x, p.y, p.px, p.py = x, y, x, y
        for c in self.bands:
            c.solve()

    def release(self, vx: float, vy: float) -> None:
        """发射：给弹丸隐含速度，解除皮筋。"""
        if not (self.projectile and self.holding):
            return
        self.projectile.p.set_velocity(vx, vy, self.dt)
        self.holding = False
        self.bands = []
        self.shot_active = True
        self.shot_steps = 0
        self._stop_timer = 0.0
        p = self.projectile.p
        self.trail = [(p.x, p.y)]

    # —— 主循环 ——

    def step(self) -> None:
        dyn = [b.p for b in self.blocks if b.alive]
        dyn += [q for q, _ in self.debris]
        if self.projectile is not None and not self.holding:
            dyn.append(self.projectile.p)
        verlet.step(dyn, self.dt)

        for _ in range(COLLISION_ITERS):
            if self.holding:
                for c in self.bands:
                    c.solve()
            self._contacts()

        if self._dead:
            self._harvest()
        self._projectile_ground()
        Dormancy.update([b.p for b in self.blocks] + [q for q, _ in self.debris], self.dt)
        self._shot_lifecycle()

    def _contacts(self) -> None:
        blocks = [b for b in self.blocks if b.alive]
        proj = self.projectile
        moving = proj is not None and not self.holding

        for b in blocks:
            j = col.resolve_ground(b, self.ground_y, self.dt)
            if j:
                self._damage(b, j)
        if moving:
            col.resolve_ground(proj, self.ground_y, self.dt)

        if moving:
            for b in blocks:
                c = col.circle_box(proj, b)
                if c is None:
                    continue
                j = col.resolve(c, self.dt)
                self._wake(c, j)
                self._damage(b, j)

        for i, a in enumerate(blocks):
            for b in blocks[i + 1 :]:
                c = col.box_box(a, b)
                if c is None:
                    continue
                j = col.resolve(c, self.dt)
                self._wake(c, j)
                self._damage(a, j)
                self._damage(b, j)

    @staticmethod
    def _wake(c: col.Contact, j: float) -> None:
        if j > WAKE_J or c.depth > WAKE_DEPTH:
            c.a.p.wake()
            c.b.p.wake()

    def _damage(self, block: Block, j: float) -> None:
        if j > 0.0 and block.impact(j):
            self._dead.append(block)

    def _harvest(self) -> None:
        """碎裂后处理：碎块、事件、连锁唤醒。"""
        for b in self._dead:
            self.events.append(BreakEvent(b.name, b.p.x, b.p.y))
            for q in make_debris(b.p.x, b.p.y, b.name, self.rng):
                q.ay = self.gravity
                self.debris.append((q, b.name))
        self.blocks = [b for b in self.blocks if b.alive]
        self._dead = []
        for b in self.blocks:  # 连锁：邻居全部唤醒，重新结算支撑
            b.p.wake()

    def _projectile_ground(self) -> None:
        """碎块的地面接触（装饰性粒子，简化处理）。"""
        for q, _ in self.debris:
            if q.y > self.ground_y:
                vx, vy = q.velocity(self.dt)
                q.translate(0.0, self.ground_y - q.y)
                if vy > 0:
                    vy = -vy * 0.15
                    vx *= 0.55
                q.set_velocity(vx, vy, self.dt)

    def _shot_lifecycle(self) -> None:
        if not self.shot_active or self.projectile is None:
            return
        self.shot_steps += 1
        p = self.projectile.p
        self.trail.append((p.x, p.y))
        speed = p.speed(self.dt)
        self._stop_timer = self._stop_timer + self.dt if speed < STOP_SPEED else 0.0
        off = p.x < -2 or p.x > self.width + 2 or p.y > self.ground_y + 3
        if off or self._stop_timer > STOP_TIME or self.shot_steps > 1600:
            self.projectile = None
            self.shot_active = False

    # —— 查询 ——

    @property
    def broken(self) -> int:
        return self.total_blocks - len(self.blocks)

    @property
    def quiet(self) -> bool:
        """是否完全静止（无弹丸、无待处理碎裂、结构全部休眠）。"""
        if self._dead:
            return False
        if self.shot_active or self.projectile is not None:
            return False
        if any(not b.p.sleeping for b in self.blocks):
            return False
        if any(not q.sleeping for q, _ in self.debris):
            return False
        return True

    def settle(self, max_steps: int = 4000) -> int:
        """跑到静止（关卡收尾用），返回实际步数。"""
        n = 0
        while n < max_steps and not self.quiet:
            self.step()
            n += 1
        return n
