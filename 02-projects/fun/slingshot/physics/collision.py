"""碰撞检测与响应：圆-方块、方块-方块、地面。

响应分两段：
1. 位置分离——同时挪 pos 和 prev（纯搬运，不注入虚假速度）；
2. 冲量近似——沿法线的恢复系数 + 切向库仑摩擦，只改 prev（改隐含速度）。
两段分开，堆叠才不会抖。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .verlet import Particle

RESTITUTION = 0.10  # 恢复系数：小，利于堆叠安定
FRICTION = 0.45  # 切向摩擦系数
MIN_RESTITUTION_V = 0.6  # 低于此接近速度不反弹（防止接触点打摆子）


class Circle:
    """弹丸：圆。"""

    __slots__ = ("p", "r")

    def __init__(self, p: Particle, r: float):
        self.p = p
        self.r = r

    @property
    def inv_mass(self) -> float:
        return self.p.inv_mass


class Box:
    """轴对齐方块（关卡结构 / 世界内的箱体）。"""

    __slots__ = ("p", "hw", "hh", "tag")

    def __init__(self, p: Particle, hw: float, hh: float, tag: str = ""):
        self.p = p
        self.hw = hw
        self.hh = hh
        self.tag = tag

    @property
    def inv_mass(self) -> float:
        return self.p.inv_mass

    @property
    def left(self) -> float:
        return self.p.x - self.hw

    @property
    def right(self) -> float:
        return self.p.x + self.hw

    @property
    def bottom(self) -> float:
        return self.p.y + self.hh

    @property
    def top(self) -> float:
        return self.p.y - self.hh


@dataclass
class Contact:
    a: object  # 圆或方块
    b: object
    nx: float  # 单位法线，由 a 指向 b
    ny: float
    depth: float


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def circle_box(c: Circle, box: Box) -> Contact | None:
    """圆心到盒面最近点：dist < r 即穿插。"""
    cx, cy = c.p.x, c.p.y
    qx = _clamp(cx, box.left, box.right)
    qy = _clamp(cy, box.top, box.bottom)
    dx, dy = cx - qx, cy - qy
    d2 = dx * dx + dy * dy
    if d2 > c.r * c.r:
        return None
    d = math.sqrt(d2)
    depth = c.r - d
    if depth <= 1e-12:
        return None  # 恰好相切不算接触
    if d > 1e-12:
        # 圆在盒外：法线由 a(box) 指向 b(circle)，即圆心方向
        return Contact(box, c, dx / d, dy / d, depth)
    # 圆心陷入盒内：沿最小穿透轴推出
    overlap_x = (box.hw + c.r) - abs(cx - box.p.x)
    overlap_y = (box.hh + c.r) - abs(cy - box.p.y)
    if overlap_x < overlap_y:
        s = 1.0 if cx >= box.p.x else -1.0
        return Contact(box, c, float(s), 0.0, overlap_x)
    s = 1.0 if cy >= box.p.y else -1.0
    return Contact(box, c, 0.0, float(s), overlap_y)


def box_box(a: Box, b: Box) -> Contact | None:
    """AABB 重叠：取穿透最小的轴作为分离方向。"""
    ox = min(a.right, b.right) - max(a.left, b.left)
    oy = min(a.bottom, b.bottom) - max(a.top, b.top)
    if ox <= 0.0 or oy <= 0.0:
        return None
    if ox < oy:
        s = 1.0 if b.p.x >= a.p.x else -1.0
        return Contact(a, b, float(s), 0.0, ox)
    s = 1.0 if b.p.y >= a.p.y else -1.0
    return Contact(a, b, 0.0, float(s), oy)


def ground_contact(body: Circle | Box, ground_y: float) -> float | None:
    """返回陷入地面的深度（>0 表示需要抬升）。"""
    if isinstance(body, Circle):
        depth = (body.p.y + body.r) - ground_y
    else:
        depth = body.bottom - ground_y
    return depth if depth > 0.0 else None


def resolve(c: Contact, dt: float) -> float:
    """位置分离 + 冲量近似，返回法线冲量大小（供结构损伤判定）。"""
    a, b = c.a, c.b
    pa, pb = a.p, b.p
    wa, wb = a.inv_mass, b.inv_mass
    total = wa + wb
    if total <= 0.0:
        return 0.0

    # 速度取分离前的隐含速度
    vax, vay = pa.velocity(dt)
    vbx, vby = pb.velocity(dt)

    # —— 第一段：位置分离（pos/prev 同挪，不产生速度；n 由 a 指向 b） ——
    pa.translate(-c.nx * c.depth * (wa / total), -c.ny * c.depth * (wa / total))
    pb.translate(c.nx * c.depth * (wb / total), c.ny * c.depth * (wb / total))

    # —— 第二段：法线冲量 + 切向摩擦（缓慢接触 e=0 非弹性死停：消除相对
    #    法向速度但不回弹；慢速冲量很小，达不到损伤阈值，静置不磨损） ——
    rvx, rvy = vbx - vax, vby - vay
    vn = rvx * c.nx + rvy * c.ny
    j = 0.0
    if vn < 0.0:
        e = RESTITUTION if vn < -MIN_RESTITUTION_V else 0.0
        j = -(1.0 + e) * vn / total
        vax -= c.nx * j * wa
        vay -= c.ny * j * wa
        vbx += c.nx * j * wb
        vby += c.ny * j * wb
        # 切向摩擦：只在有法线冲量时生效，防止接触面打滑
        rvx, rvy = vbx - vax, vby - vay
        vt = rvx * -c.ny + rvy * c.nx  # 切向分量
        jt = _clamp(-vt / total, -FRICTION * j, FRICTION * j)
        vax -= -c.ny * jt * wa
        vay -= c.nx * jt * wa
        vbx += -c.ny * jt * wb
        vby += c.nx * jt * wb

    pa.set_velocity(vax, vay, dt)
    pb.set_velocity(vbx, vby, dt)
    return j


def resolve_ground(body: Circle | Box, ground_y: float, dt: float) -> float:
    """地面响应：抬升 + 法向止动 + 摩擦。返回法线冲量大小。"""
    pa = body.p
    if pa.inv_mass <= 0.0:
        return 0.0
    depth = ground_contact(body, ground_y)
    if depth is None:
        return 0.0
    vx, vy = pa.velocity(dt)
    pa.translate(0.0, -depth)  # 抬出地面
    j = 0.0
    if vy > MIN_RESTITUTION_V:  # y 向下为正
        # 损伤度量 = 接近速度 × 柔性(w=1/m)：同材质小块更脆，轻玻璃一摔就碎
        j = (1.0 + RESTITUTION) * vy * pa.inv_mass  # 静止地面 w=0
        vy = -RESTITUTION * vy
    elif vy > 0.0:
        vy = 0.0  # 缓慢着地「死停」：无冲量、静置不磨损
    if vx:
        vx *= 0.92  # 接触面滑动/滚动摩擦
    pa.set_velocity(vx, vy, dt)
    return j


def aabb_touch(a: Box, b: Box, slop: float = 1e-6) -> bool:
    """两盒是否接触/重叠（关卡合法性校验用）。"""
    return not (
        a.right < b.left - slop
        or b.right < a.left - slop
        or a.bottom < b.top - slop
        or b.bottom < a.top - slop
    )
