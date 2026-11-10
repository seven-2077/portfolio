"""双摆混沌模拟 · 物理核心包。

模块分工：
    ode.py       运动方程（Lagrange 推导 → 一阶标准形式）
    energy.py    动能 / 势能 / 总能量（数值质量监测）
    integrate.py RK4 定步长积分器 + 状态快照
    trace.py     轨迹采集（支持两组微差初值并行对比）
"""

from . import energy, integrate, ode, trace

__all__ = ["ode", "energy", "integrate", "trace"]
