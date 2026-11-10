"""能量计算：动能、势能、总能量。

用途有二：
    1. 数值质量监测 —— 自治系统的总能量是运动常数，RK4 的能量漂移
       直接反映积分误差的大小（漂移小 ≈ 方程没解错）；
    2. 初始能量标定 —— demo 与测试用 E0 归一化漂移量。

公式（与 ode.py 的 Lagrange 推导同源，最低点为势能零点）：

    T = ½ (m1+m2) l1² ω1² + ½ m2 l2² ω2² + m2 l1 l2 ω1 ω2 cos(θ1-θ2)
    V = (m1+m2) g l1 (1-cosθ1) + m2 g l2 (1-cosθ2)
    E = T + V

边界约定：静止且双杆下垂（θ1=θ2=0, ω=0）时 T=V=E=0。
"""

from __future__ import annotations

from math import cos
from typing import Sequence

from .ode import DEFAULT, Params

__all__ = ["kinetic", "potential", "total", "drift"]


def kinetic(state: Sequence[float], params: Params = DEFAULT) -> float:
    """动能 T ≥ 0。含交叉项 m2 l1 l2 ω1 ω2 cosδ（两摆的速度耦合）。"""
    th1, w1, th2, w2 = state
    m1, m2 = params.m1, params.m2
    l1, l2 = params.l1, params.l2

    return (
        0.5 * (m1 + m2) * l1 * l1 * w1 * w1
        + 0.5 * m2 * l2 * l2 * w2 * w2
        + m2 * l1 * l2 * w1 * w2 * cos(th1 - th2)
    )


def potential(state: Sequence[float], params: Params = DEFAULT) -> float:
    """势能 V ≥ 0（最低点取零，1-cosθ ≥ 0 保证非负）。"""
    th1, _w1, th2, _w2 = state
    m1, m2 = params.m1, params.m2
    l1, l2, g = params.l1, params.l2, params.g

    return (m1 + m2) * g * l1 * (1.0 - cos(th1)) + m2 * g * l2 * (1.0 - cos(th2))


def total(state: Sequence[float], params: Params = DEFAULT) -> float:
    """总能量 E = T + V，自治系统下的运动常数。"""
    return kinetic(state, params) + potential(state, params)


def drift(energies: Sequence[float]) -> list[float]:
    """相对首帧的能量漂移序列 [E_i - E_0]。"""
    if not energies:
        return []
    e0 = energies[0]
    return [e - e0 for e in energies]
