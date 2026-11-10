"""Gray–Scott 反应扩散模型（显式有限差分，纯标准库）。

方程（无量纲形式）::

    ∂U/∂t = Du·∇²U − U·V² + F·(1 − U)
    ∂V/∂t = Dv·∇²V + U·V² − (F + k)·V

U 是被消耗的“反应物”，V 是自催化的“产物”；F 为补给速率（feed），
k 为消耗速率（kill）。局部只有反应 + 扩散两条简单规则，全局却能长出
斑点、条纹、蠕虫——Turing 1952 图案发生学的数值重现。

实现要点：
    * 显式 FTCS 更新，拉普拉斯支持 5 点 / 9 点（Mehrstellen）两种模板；
    * 邻居下标在构造时预计算，内层循环零分配，双缓冲交换；
    * 每步把浓度裁剪进 [0, 1]，越界/非有限值一律兜底，保证数值稳定。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RDPreset:
    """一组 feed/kill 配方（Pearson 1993 参数空间中的典型区域）。"""

    name: str
    label: str
    feed: float
    kill: float
    note: str


PRESETS: dict[str, RDPreset] = {
    p.name: p
    for p in (
        RDPreset("spots", "斑点型", 0.0367, 0.0649, "自复制斑点：孤立圆点不断分裂（mitosis 区）"),
        RDPreset("stripes", "条纹型", 0.0300, 0.0620, "迷宫条纹：细长条纹蜿蜒交织（labyrinth 区）"),
        RDPreset("worms", "蠕虫型", 0.0260, 0.0550, "低补给低消耗：蠕虫状结构密集蔓延（λ 区）"),
    )
}


class GrayScott:
    """Gray–反应扩散 U/V 浓度场：可配 feed/kill/扩散系数与拉普拉斯模板。"""

    def __init__(
        self,
        width: int,
        height: int,
        *,
        feed: float = 0.037,
        kill: float = 0.06,
        du: float = 0.16,
        dv: float = 0.08,
        dt: float = 1.0,
        lap: str = "9",
        wrap: bool = True,
        seed_size: int | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"网格尺寸必须为正，收到 {width}x{height}")
        if lap not in ("5", "9"):
            raise ValueError(f"拉普拉斯模板只能是 '5' 或 '9'，收到 {lap!r}")
        if du < 0 or dv < 0 or dt <= 0:
            raise ValueError("扩散系数须非负，dt 须为正")
        if not (0 <= feed <= 1 and 0 <= kill <= 1):
            raise ValueError("feed/kill 须落在 [0, 1]")
        self.width = int(width)
        self.height = int(height)
        self.feed = float(feed)
        self.kill = float(kill)
        self.du = float(du)
        self.dv = float(dv)
        self.dt = float(dt)
        self.lap = lap
        self.wrap = bool(wrap)
        self.generation = 0

        n = self.width * self.height
        self.u = [1.0] * n
        self.v = [0.0] * n
        self._bu = [0.0] * n
        self._bv = [0.0] * n
        self._nb = self._build_neighbors()
        self._seed(seed_size)

    # ---------------------------------------------------------------- 初始化
    def _build_neighbors(self) -> tuple[list[int], ...]:
        """预计算每个格子的上/下/左/右(/对角) 邻居下标，避免热循环里的取模。"""
        w, h, wrap = self.width, self.height, self.wrap
        n = w * h
        U, D, L, R = [0] * n, [0] * n, [0] * n, [0] * n
        diag = self.lap == "9"
        UL = UR = DL = DR = None
        if diag:
            UL, UR, DL, DR = [0] * n, [0] * n, [0] * n, [0] * n
        for y in range(h):
            ym = (y - 1) % h if wrap else max(y - 1, 0)
            yp = (y + 1) % h if wrap else min(y + 1, h - 1)
            for x in range(w):
                xm = (x - 1) % w if wrap else max(x - 1, 0)
                xp = (x + 1) % w if wrap else min(x + 1, w - 1)
                i = y * w + x
                U[i], D[i] = ym * w + x, yp * w + x
                L[i], R[i] = y * w + xm, y * w + xp
                if diag:
                    UL[i], UR[i] = ym * w + xm, ym * w + xp
                    DL[i], DR[i] = yp * w + xm, yp * w + xp
        return (U, D, L, R) if not diag else (U, D, L, R, UL, UR, DL, DR)

    def _seed(self, seed_size: int | None) -> None:
        """5 点播种：四象限 + 中心各一方块，U=0.50、V=0.25（其余 U=1、V=0）。

        比例定位 + 完全确定性：小网格自动钳进边界，几百步内图案即可铺满全场。
        """
        w, h = self.width, self.height
        bw = int(seed_size) if seed_size else max(6, min(w, h) // 6)
        bw = max(2, min(bw, w, h))
        points = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75), (0.5, 0.5))
        for fx, fy in points:
            cx, cy = int(w * fx), int(h * fy)
            x0 = max(0, min(cx - bw // 2, w - bw))
            y0 = max(0, min(cy - bw // 2, h - bw))
            for y in range(y0, y0 + bw):
                base = y * w
                for x in range(x0, x0 + bw):
                    self.u[base + x] = 0.50
                    self.v[base + x] = 0.25

    @classmethod
    def from_preset(cls, width: int, height: int, name: str, **overrides: object) -> "GrayScott":
        """按预设名（spots/stripes/worms）建场，可再覆盖任意参数。"""
        if name not in PRESETS:
            raise KeyError(f"未收录预设 {name!r}，可用：{', '.join(PRESETS)}")
        p = PRESETS[name]
        params: dict[str, object] = {"feed": p.feed, "kill": p.kill}
        params.update(overrides)
        return cls(width, height, **params)  # type: ignore[arg-type]

    # ---------------------------------------------------------------- 演化
    def step(self) -> None:
        """显式有限差分推进一个时间步，并把 U/V 裁剪进 [0, 1]。"""
        u, v = self.u, self.v
        bu, bv = self._bu, self._bv
        feed, kill, fk = self.feed, self.kill, self.feed + self.kill
        au, av = self.du * self.dt, self.dv * self.dt
        n = len(u)
        U, D, L, R, *rest = self._nb
        if rest:  # 9 点模板：4 正交 + 4 对角（Mehrstellen 加权）
            UL, UR, DL, DR = rest
            s6 = 1.0 / 6.0
            for i in range(n):
                ui, vi = u[i], v[i]
                lu = (4.0 * (u[U[i]] + u[D[i]] + u[L[i]] + u[R[i]])
                      + u[UL[i]] + u[UR[i]] + u[DL[i]] + u[DR[i]] - 20.0 * ui) * s6
                lv = (4.0 * (v[U[i]] + v[D[i]] + v[L[i]] + v[R[i]])
                      + v[UL[i]] + v[UR[i]] + v[DL[i]] + v[DR[i]] - 20.0 * vi) * s6
                uvv = ui * vi * vi
                bu[i] = min(1.0, max(0.0, ui + au * lu - uvv + feed * (1.0 - ui)))
                bv[i] = min(1.0, max(0.0, vi + av * lv + uvv - fk * vi))
        else:  # 5 点模板
            for i in range(n):
                ui, vi = u[i], v[i]
                lu = u[U[i]] + u[D[i]] + u[L[i]] + u[R[i]] - 4.0 * ui
                lv = v[U[i]] + v[D[i]] + v[L[i]] + v[R[i]] - 4.0 * vi
                uvv = ui * vi * vi
                bu[i] = min(1.0, max(0.0, ui + au * lu - uvv + feed * (1.0 - ui)))
                bv[i] = min(1.0, max(0.0, vi + av * lv + uvv - fk * vi))
        self.u, self.v = bu, bv
        self._bu, self._bv = u, v
        self.generation += 1

    def run(self, n: int) -> "GrayScott":
        """批量推进 n 步，返回自身。"""
        if n < 0:
            raise ValueError("步数不能为负")
        for _ in range(n):
            self.step()
        return self

    # ---------------------------------------------------------------- 观测
    def field_u(self) -> tuple[float, ...]:
        return tuple(self.u)

    def field_v(self) -> tuple[float, ...]:
        return tuple(self.v)

    def stats(self) -> dict[str, float]:
        """统计特征：均值、V 场边缘密度（平均梯度模）、V 占据率。"""
        u, v = self.u, self.v
        U, D, L, _R = self._nb[:4]
        n = len(u)
        sum_u = sum_v = edge = 0.0
        occupied = 0
        for i in range(n):
            ui, vi = u[i], v[i]
            sum_u += ui
            sum_v += vi
            edge += abs(vi - v[U[i]]) + abs(vi - v[L[i]])
            if vi > 0.1:
                occupied += 1
        return {
            "generation": float(self.generation),
            "mean_u": sum_u / n,
            "mean_v": sum_v / n,
            "edge_density": edge / (2 * n),
            "occupied": occupied / n,
        }
