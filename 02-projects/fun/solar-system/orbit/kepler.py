"""开普勒方程数值求解：M = E - e·sin(E)（弧度制）。

背景
----
开普勒方程把"均匀流逝的时间"（平近点角 M）映射为椭圆轨道上的
真实位置（偏近点角 E）。它是超越方程，除 e = 0 外没有解析解，
从开普勒、牛顿到今天都只能数值求解——本模块用牛顿迭代。

收敛判据 |ΔE| < 1e-12（弧度，约 6e-6 度），带迭代上限 max_iter
与二分法兜底（发散保护）：即使牛顿迭代失效，也保证拿到正确根。
"""

from __future__ import annotations

import math

__all__ = ["solve_kepler", "true_anomaly", "orbital_radius", "KeplerError"]


class KeplerError(RuntimeError):
    """牛顿迭代与兜底二分均未在限制内收敛（正常情况下不会触发）。"""


def solve_kepler(M: float, e: float, tol: float = 1e-12, max_iter: int = 60) -> float:
    """求解开普勒方程  E - e·sin(E) = M。

    参数
    ----
    M        平近点角（弧度，任意实数，内部用 math.remainder 归一到 [-π, π]）
    e        偏心率，需满足 0 <= e < 1（椭圆轨道）
    tol      |ΔE| 收敛阈值（弧度），默认 1e-12
    max_iter 牛顿迭代上限；超限或发散时转入二分兜底

    返回
    ----
    偏近点角 E（弧度），落在与 M 相同的半周期 [-π, π] 内。
    """
    if not 0.0 <= e < 1.0:
        raise ValueError(f"偏心率需满足 0 <= e < 1，收到 e={e}")
    if tol <= 0.0:
        raise ValueError("tol 必须为正")
    if max_iter < 0:
        raise ValueError("max_iter 不能为负")

    M = math.remainder(M, 2.0 * math.pi)

    # 牛顿迭代：f(E) = E - e·sinE - M，f'(E) = 1 - e·cosE >= 1 - e > 0
    E = M + e * math.sin(M)  # 经典初值（JPL 近似历表同样采用）
    converged = False
    for _ in range(max_iter):
        if not math.isfinite(E):
            break
        denom = 1.0 - e * math.cos(E)
        # e < 1 时 denom >= 1 - e > 0，理论恒正；此处仍留发散保护
        if denom < 1e-15:
            break
        delta = (E - e * math.sin(E) - M) / denom
        if not math.isfinite(delta):
            break
        E -= delta
        if abs(delta) < tol:
            converged = True
            break

    if converged:
        return E

    # 残差可能已经足够小（例如 e=0 时 E 恒等于 M，max_iter=0 的场景）
    if abs(E - e * math.sin(E) - M) < tol:
        return E

    # 兜底：二分法。由 |e·sinE| <= e 可知根必落在 [M - e, M + e] 内，
    # 且 f(M - e) <= 0 <= f(M + e)，括号恒有效——这就是"发散保护"。
    lo, hi = M - e, M + e
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid == lo or mid == hi:
            break
        if mid - e * math.sin(mid) - M > 0.0:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            return 0.5 * (lo + hi)

    raise KeplerError(f"开普勒方程未收敛：M={M!r}, e={e!r}, tol={tol!r}")


def true_anomaly(E: float, e: float) -> float:
    """由偏近点角 E 求真近点角 ν（弧度）：tan ν = √(1-e²)·sinE / (cosE - e)。"""
    return math.atan2(math.sqrt(1.0 - e * e) * math.sin(E), math.cos(E) - e)


def orbital_radius(a: float, E: float, e: float) -> float:
    """轨道半径 r = a·(1 - e·cosE)（长度单位与 a 一致，如 AU）。"""
    return a * (1.0 - e * math.cos(E))
