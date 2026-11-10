"""轨迹采集：单组仿真 + 两组微差初值并行对比。

核心卖点在这里落地：两组初值只差 delta（默认 1e-4 rad），同步积分同一套
方程，逐帧记录状态距离与端点（摆球）轨迹，直到距离超过阈值 —— 蝴蝶效应
的「分岔时刻」由此读出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, sin, sqrt
from typing import Sequence

from .integrate import RK4, Snapshot
from .ode import DEFAULT, Params

__all__ = ["Run", "PairResult", "tip_positions", "state_distance", "simulate", "run_pair", "run_pair_with_delta"]

# 端点轨迹四元组：(x1, y1, x2, y2)，第一/第二摆球的世界坐标
Tip = tuple[float, float, float, float]


def tip_positions(state: Sequence[float], params: Params = DEFAULT) -> Tip:
    """由状态算两个摆球位置（y 轴向上，支点为原点）。"""
    th1, _w1, th2, _w2 = state
    x1 = params.l1 * sin(th1)
    y1 = -params.l1 * cos(th1)
    x2 = x1 + params.l2 * sin(th2)
    y2 = y1 - params.l2 * cos(th2)
    return (x1, y1, x2, y2)


def state_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """两状态的欧氏距离（4 维相空间中的直线距离）。"""
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


@dataclass
class Run:
    """一次完整仿真的轨迹记录。"""

    label: str
    dt: float
    params: Params = DEFAULT
    times: list[float] = field(default_factory=list)
    states: list[tuple[float, ...]] = field(default_factory=list)
    energies: list[float] = field(default_factory=list)
    tips: list[Tip] = field(default_factory=list)

    def max_energy_drift(self) -> float:
        """全程最大能量漂移 max|E(t) - E(0)|。"""
        if not self.energies:
            return 0.0
        e0 = self.energies[0]
        return max(abs(e - e0) for e in self.energies)

    def relative_energy_drift(self) -> float:
        """相对能量漂移（以 |E0| 归一；E0≈0 时退化为全程能量尺度归一）。"""
        if not self.energies:
            return 0.0
        e0 = self.energies[0]
        scale = abs(e0) if abs(e0) > 1e-12 else max(abs(e) for e in self.energies) or 1.0
        return self.max_energy_drift() / scale


def simulate(
    state0: Sequence[float],
    t_end: float = 10.0,
    dt: float = 1e-3,
    params: Params = DEFAULT,
    label: str = "run",
    t0: float = 0.0,
) -> Run:
    """单组初值仿真：积分并采集状态、能量、端点轨迹。"""
    rk = RK4(params=params, dt=dt)
    snaps: list[Snapshot] = rk.integrate(state0, t0=t0, t_end=t_end)

    run = Run(label=label, dt=dt, params=params)
    for s in snaps:
        run.times.append(s.t)
        run.states.append(s.state)
        run.energies.append(s.energy)
        run.tips.append(tip_positions(s.state, params))
    return run


@dataclass
class PairResult:
    """两组初值的并行对比结果（时间网格对齐，逐帧可比）。"""

    run_a: Run
    run_b: Run
    distances: list[float] = field(default_factory=list)

    @property
    def times(self) -> list[float]:
        return self.run_a.times

    @property
    def initial_distance(self) -> float:
        return self.distances[0] if self.distances else 0.0

    @property
    def final_distance(self) -> float:
        return self.distances[-1] if self.distances else 0.0

    def bifurcation_time(self, threshold: float = 0.1) -> float | None:
        """状态距离首次超过 threshold 的时刻；从未超过返回 None。"""
        for t, d in zip(self.times, self.distances):
            if d > threshold:
                return t
        return None


def run_pair(
    state0_a: Sequence[float],
    state0_b: Sequence[float],
    t_end: float = 10.0,
    dt: float = 1e-3,
    params: Params = DEFAULT,
    labels: tuple[str, str] = ("A", "B"),
) -> PairResult:
    """两组初值同步积分，逐帧记录相空间距离与端点轨迹。"""
    run_a = simulate(state0_a, t_end=t_end, dt=dt, params=params, label=labels[0])
    run_b = simulate(state0_b, t_end=t_end, dt=dt, params=params, label=labels[1])
    distances = [state_distance(sa, sb) for sa, sb in zip(run_a.states, run_b.states)]
    return PairResult(run_a=run_a, run_b=run_b, distances=distances)


def run_pair_with_delta(
    base_state: Sequence[float],
    delta: float = 1e-4,
    index: int = 0,
    t_end: float = 10.0,
    dt: float = 1e-3,
    params: Params = DEFAULT,
) -> PairResult:
    """从同一基准初值出发，扰动第 index 个分量 delta 作为第二组。

    index=0 即扰动 θ1；两组初始距离恰为 |delta|。
    """
    state_b = list(base_state)
    state_b[index] += delta
    return run_pair(base_state, state_b, t_end=t_end, dt=dt, params=params)
