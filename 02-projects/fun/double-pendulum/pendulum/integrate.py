"""RK4 定步长积分器，逐步记录状态快照与能量。

经典四阶 Runge–Kutta（单步、四次求值、局部截断误差 O(dt⁵)、全局 O(dt⁴)）：

    k1 = f(y,          t)
    k2 = f(y + dt/2·k1, t + dt/2)
    k3 = f(y + dt/2·k2, t + dt/2)
    k4 = f(y + dt·k3,   t + dt)
    y_{n+1} = y + dt/6 · (k1 + 2k2 + 2k3 + k4)

变步长扩展位
------------
Integrator 基类暴露两处扩展点，未来接 RK45 / Dormand–Prince 等自适应方法时
调用侧（trace.py）无需改动：

    step()        —— 单步推进（子类必须实现）
    suggest_dt()  —— 嵌入式误差估计 → 下一步步长（当前未实现，直接抛错）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from . import energy as _energy
from .ode import DEFAULT, Params, derivatives as _default_deriv

__all__ = ["Snapshot", "Integrator", "RK4"]

# 导数函数契约：f(state, params) -> tuple[float, ...]
Deriv = Callable[[Sequence[float], Params], Sequence[float]]
# 能量函数契约：e(state) -> float
EnergyFn = Callable[[Sequence[float]], float]


@dataclass(frozen=True)
class Snapshot:
    """某一时刻的完整快照：时间 + 状态 + 总能量。"""

    t: float
    state: tuple[float, ...]
    energy: float


class Integrator:
    """积分器基类：定步长接口 + 变步长扩展位。"""

    def step(self, state: Sequence[float], t: float, dt: float) -> tuple[float, ...]:
        """推进一步，返回新状态（子类实现）。"""
        raise NotImplementedError

    def suggest_dt(self, state: Sequence[float], t: float, tol: float = 1e-6) -> float:
        """变步长扩展位：由嵌入式误差估计推荐下一步步长。

        当前仅实现定步长 RK4，此接口为 RK45 / Dormand–Prince 预留。
        """
        raise NotImplementedError("变步长为扩展位：需实现嵌入式误差估计（如 RK45）")


class RK4(Integrator):
    """经典四阶 Runge–Kutta，定步长。

    Parameters
    ----------
    deriv : 右端函数 f(state, params)，默认双摆方程
    params : 物理参数
    dt : 定步长（s）
    energy_fn : 快照能量函数，默认取双摆总能量；
                换用其他系统（如单摆校验）时传入自定义函数
    """

    def __init__(
        self,
        deriv: Deriv = _default_deriv,
        params: Params = DEFAULT,
        dt: float = 1e-3,
        energy_fn: EnergyFn | None = None,
    ) -> None:
        if dt <= 0:
            raise ValueError(f"dt 必须为正，得到 {dt}")
        self.deriv = deriv
        self.params = params
        self.dt = dt
        self.energy_fn: EnergyFn = energy_fn or (lambda s: _energy.total(s, params))

    def step(self, state: Sequence[float], t: float, dt: float | None = None) -> tuple[float, ...]:
        """RK4 单步推进。dt 缺省用构造时的定步长。"""
        h = self.dt if dt is None else dt
        f = self.deriv
        p = self.params

        y = tuple(float(x) for x in state)
        k1 = tuple(f(y, p))
        k2 = tuple(f(tuple(y[i] + 0.5 * h * k1[i] for i in range(len(y))), p))
        k3 = tuple(f(tuple(y[i] + 0.5 * h * k2[i] for i in range(len(y))), p))
        k4 = tuple(f(tuple(y[i] + h * k3[i] for i in range(len(y))), p))

        return tuple(y[i] + (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) for i in range(len(y)))

    def integrate(
        self,
        state0: Sequence[float],
        t0: float = 0.0,
        t_end: float = 10.0,
    ) -> list[Snapshot]:
        """从 t0 积分到 t0 + n·dt（n = round((t_end-t0)/dt)），返回逐步快照列表。

        快照含初始帧，共 n+1 帧；时间网格用 t0 + i·dt 计算，避免逐步累加的
        浮点漂移。每帧附带 energy_fn 记录的能量。
        """
        n = int(round((t_end - t0) / self.dt))
        if n < 0:
            raise ValueError(f"t_end ({t_end}) 不能早于 t0 ({t0})")

        snaps: list[Snapshot] = []
        state = tuple(float(x) for x in state0)
        snaps.append(Snapshot(t0, state, self.energy_fn(state)))

        for i in range(1, n + 1):
            state = self.step(state, t0 + (i - 1) * self.dt)
            t = t0 + i * self.dt
            snaps.append(Snapshot(t, state, self.energy_fn(state)))
        return snaps
