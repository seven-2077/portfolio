"""双摆运动方程：从 Lagrange 力学推导到一阶标准形式。

状态向量约定（全项目统一）
------------------------
    y = (θ1, ω1, θ2, ω2)
    θ：杆与竖直**向下**方向的夹角（rad），ω = dθ/dt（角速度）

Lagrange 推导（关键步骤）
------------------------
两根无质量刚性杆 l1、l2，质点 m1、m2，支点固定。y 轴向上：

    位置   x1 = l1 sinθ1            y1 = -l1 cosθ1
           x2 = x1 + l2 sinθ2       y2 = y1 - l2 cosθ2

    速度² v1² = l1² ω1²
           v2² = l1² ω1² + l2² ω2² + 2 l1 l2 ω1 ω2 cosδ，  记 δ ≡ θ1 - θ2

    动能   T = ½ m1 v1² + ½ m2 v2²
           = ½ (m1+m2) l1² ω1² + ½ m2 l2² ω2² + m2 l1 l2 ω1 ω2 cosδ

    势能   V = (m1+m2) g l1 (1-cosθ1) + m2 g l2 (1-cosθ2)   （最低点取零）

对 θ1、θ2 写 Euler-Lagrange 方程  d/dt(∂L/∂ωi) - ∂L/∂θi = 0，把**含角加速度的项
全部收集到左边**（惯性耦合），其余放右边，得到质量矩阵形式：

    [ (m1+m2) l1²    m2 l1 l2 cosδ ] [ω̇1]   [ -m2 l1 l2 ω2² sinδ - (m1+m2) g l1 sinθ1 ]
    [ m2 l1 l2 cosδ   m2 l2²       ] [ω̇2] = [  m2 l1 l2 ω1² sinδ - m2 g l2 sinθ2       ]

    （该矩阵正是 T 关于 ω 的 Hessian，天然对称）

2×2 矩阵求逆（解析式，零依赖，不引第三方线性代数）：

    det = (m1+m2) l1² · m2 l2² - (m2 l1 l2 cosδ)²
        = m2 l1² l2² [ (m1+m2) - m2 cos²δ ]
        = m2 l1² l2² ( m1 + m2 sin²δ )  > 0   恒成立（m1, l1, l2 > 0）

    ω̇1 = (  m2 l2²        · F1 - m2 l1 l2 cosδ · F2) / det
    ω̇2 = ( -m2 l1 l2 cosδ · F1 + (m1+m2) l1²    · F2) / det

守恒结构：方程不含显式 t，系统自治 → 总能量 E = T + V 是运动常数，
这正是我们用 energy.py 监测数值质量的依据。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin
from typing import Sequence

__all__ = ["Params", "DEFAULT", "derivatives", "single_pendulum_derivatives"]


@dataclass(frozen=True)
class Params:
    """双摆物理参数（不可变，可安全共享）。"""

    m1: float = 1.0   # 第一摆球质量 (kg)
    m2: float = 1.0   # 第二摆球质量 (kg)
    l1: float = 1.0   # 第一杆长 (m)
    l2: float = 1.0   # 第二杆长 (m)
    g: float = 9.81   # 重力加速度 (m/s²)


DEFAULT = Params()

# 状态向量类型：(θ1, ω1, θ2, ω2)
State = tuple[float, float, float, float]


def derivatives(state: Sequence[float], params: Params = DEFAULT) -> State:
    """双摆右端函数：y = (θ1, ω1, θ2, ω2) ↦ dy/dt。

    把两个二阶 ODE θ̈1 = f1(...)、θ̈2 = f2(...) 化为 4 个一阶方程：

        dθ1/dt = ω1
        dω1/dt = α1(θ1, ω1, θ2, ω2)
        dθ2/dt = ω2
        dω2/dt = α2(θ1, ω1, θ2, ω2)
    """
    th1, w1, th2, w2 = state
    m1, m2 = params.m1, params.m2
    l1, l2, g = params.l1, params.l2, params.g

    sd = sin(th1 - th2)          # sinδ
    cd = cos(th1 - th2)          # cosδ

    # --- 质量矩阵 M（对称 2×2）与右端力向量 F ---
    m11 = (m1 + m2) * l1 * l1
    m12 = m2 * l1 * l2 * cd
    m22 = m2 * l2 * l2

    f1 = -m2 * l1 * l2 * w2 * w2 * sd - (m1 + m2) * g * l1 * sin(th1)
    f2 = m2 * l1 * l2 * w1 * w1 * sd - m2 * g * l2 * sin(th2)

    # --- 解析求逆：det = m2 l1² l2² (m1 + m2 sin²δ)，恒大于 0，无除零风险 ---
    det = m11 * m22 - m12 * m12

    a1 = (m22 * f1 - m12 * f2) / det
    a2 = (m11 * f2 - m12 * f1) / det

    return (w1, a1, w2, a2)


def single_pendulum_derivatives(state: Sequence[float], params: Params = DEFAULT) -> tuple[float, float]:
    """单摆右端函数（校验用基准系统）：y = (θ, ω)。

        dθ/dt = ω
        dω/dt = -(g/l1) sinθ

    小角度（sinθ ≈ θ）时解析周期 T = 2π √(l/g)，测试用它标定积分器精度。
    """
    th, w = state
    return (w, -(params.g / params.l1) * sin(th))
