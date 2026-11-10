"""SVG 输出：轨迹对比图 / 能量漂移曲线 / 分岔距离对数曲线。

纯字符串拼装 SVG，零依赖。三张图的共同约定：

    颜色 A = #e63946（红），颜色 B = #1d7874（青）—— 两组初值贯穿全项目
    轨迹图用「分段时间渐变」实现透明叠加：路径切成小段，逐段加深透明度，
    时间早 → 淡，时间晚 → 浓，两色交叠处自然混色。
"""

from __future__ import annotations

import math
from pathlib import Path

from pendulum.trace import PairResult

__all__ = [
    "trajectory_svg",
    "energy_svg",
    "divergence_svg",
    "write_all",
    "TRAJECTORY_FILE",
    "ENERGY_FILE",
    "DIVERGENCE_FILE",
]

COLOR_A = "#e63946"
COLOR_B = "#1d7874"
COLOR_C = "#7b2cbf"
_FONT = "Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
_BG = "#fbfbf9"
_GRID = "#ececea"
_TEXT = "#1d1d1f"
_MUTED = "#6e6e73"

TRAJECTORY_FILE = "trajectory_compare.svg"
ENERGY_FILE = "energy_drift.svg"
DIVERGENCE_FILE = "divergence_log.svg"


# ---------------------------------------------------------------- 基础工具

def _svg_open(width: int, height: int, title: str, subtitle: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}">\n'
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>\n'
        f'<text x="{width // 2}" y="30" text-anchor="middle" font-size="19" '
        f'font-weight="600" fill="{_TEXT}">{title}</text>\n'
        f'<text x="{width // 2}" y="52" text-anchor="middle" font-size="12.5" '
        f'fill="{_MUTED}">{subtitle}</text>\n'
    )


def _nice_ticks(lo: float, hi: float, n: int = 6) -> list[float]:
    """在 [lo, hi] 内生成 n 个「整数步长」的刻度。"""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(n, 1)
    mag = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= mult * mag:
            step = mult * mag
            break
    else:
        step = mag
    start = math.ceil(lo / step - 1e-9) * step
    ticks = []
    v = start
    while v <= hi + 1e-9:
        ticks.append(0.0 if abs(v) < step * 1e-9 else v)
        v += step
    return ticks


def _fmt_tick(v: float) -> str:
    if v == 0.0:
        return "0"
    if 0.01 <= abs(v) < 10000.0:
        return f"{v:g}"
    return f"{v:.1e}"


class _Mapper:
    """世界坐标（y 向上）→ SVG 画布坐标（y 向下），等比例缩放并居中。"""

    def __init__(self, xmin, xmax, ymin, ymax, px0, py0, px1, py1):
        self.xmin, self.ymax = xmin, ymax
        s = min((px1 - px0) / (xmax - xmin), (py1 - py0) / (ymax - ymin))
        self.s = s
        self.ox = px0 + ((px1 - px0) - (xmax - xmin) * s) / 2.0
        self.oy = py0 + ((py1 - py0) - (ymax - ymin) * s) / 2.0

    def xy(self, x: float, y: float) -> tuple[float, float]:
        return (self.ox + (x - self.xmin) * self.s, self.oy + (self.ymax - y) * self.s)


def _polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _decimate(points: list, max_points: int = 2500) -> list:
    """等间隔抽稀（保留首尾），控制曲线 SVG 的文件体积。"""
    n = len(points)
    if n <= max_points:
        return points
    step = math.ceil(n / max_points)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


# ---------------------------------------------------------------- 图 1：轨迹对比

def trajectory_svg(pair: PairResult, width: int = 880, height: int = 880) -> str:
    """双轨迹对比图：两色、透明叠加、随时间渐变的摆球 2 端点轨迹。"""
    run_a, run_b = pair.run_a, pair.run_b
    params = run_a.params
    r = params.l1 + params.l2

    px0, py0, px1, py1 = 50, 66, width - 50, height - 110
    mapper = _Mapper(-1.15 * r, 1.15 * r, -1.2 * r, 1.2 * r, px0, py0, px1, py1)

    parts = [_svg_open(width, height, "双摆轨迹对比：Δθ₁ = 1e-4 rad，几秒后彻底分道扬镳",
                       f"两组初值同步积分 · 摆球 2 端点轨迹 · 实线随时间加深 · "
                       f"t = 0 → {run_a.times[-1]:g} s，dt = {run_a.dt * 1000:g} ms")]

    # 网格（步长 = 半杆长单位）与支点
    step = r / 2.0
    gx = math.ceil(mapper.xmin / step) * step
    while gx <= 1.15 * r + 1e-9:
        sx, _ = mapper.xy(gx, 0.0)
        parts.append(f'<line x1="{sx:.1f}" y1="{py0}" x2="{sx:.1f}" y2="{py1}" '
                     f'stroke="#e4e4e1" stroke-width="1"/>')
        gx += step
    gy = math.ceil(-1.2 * r / step) * step
    while gy <= 1.2 * r + 1e-9:
        _, sy = mapper.xy(0.0, gy)
        parts.append(f'<line x1="{px0}" y1="{sy:.1f}" x2="{px1}" y2="{sy:.1f}" '
                     f'stroke="#e4e4e1" stroke-width="1"/>')
        gy += step
    # 水平参考线（y = 0，支点高度）
    _, sy0 = mapper.xy(0.0, 0.0)
    parts.append(f'<line x1="{px0}" y1="{sy0:.1f}" x2="{px1}" y2="{sy0:.1f}" '
                 f'stroke="#b8b8b5" stroke-width="1.2"/>')

    # 两组轨迹：分段 + 时间渐变透明度
    chunk = 26
    for run, color in ((run_a, COLOR_A), (run_b, COLOR_B)):
        pts = [mapper.xy(tip[2], tip[3]) for tip in run.tips]  # 摆球 2 端点
        if len(pts) < 2:
            continue
        n_chunks = max(1, math.ceil((len(pts) - 1) / chunk))
        for k in range(n_chunks):
            i0, i1 = k * chunk, min(len(pts) - 1, (k + 1) * chunk)
            seg = pts[i0:i1 + 1]
            if len(seg) < 2:
                continue
            alpha = 0.20 + 0.75 * (k / (n_chunks - 1) if n_chunks > 1 else 1.0)
            parts.append(
                f'<polyline fill="none" stroke="{color}" stroke-opacity="{alpha:.2f}" '
                f'stroke-width="1.8" stroke-linecap="round" '
                f'points="{_polyline(seg)}"/>'
            )
        # 起点标记
        sx, sy = pts[0]
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="none" '
                     f'stroke="{color}" stroke-width="1.6"/>')

    # 终态摆杆 + 摆球（直观看到「此刻它俩差多远」）
    for run, color in ((run_a, COLOR_A), (run_b, COLOR_B)):
        x1, y1, x2, y2 = run.tips[-1]
        p0 = mapper.xy(0.0, 0.0)
        p1 = mapper.xy(x1, y1)
        p2 = mapper.xy(x2, y2)
        parts.append(
            f'<line x1="{p0[0]:.1f}" y1="{p0[1]:.1f}" x2="{p1[0]:.1f}" y2="{p1[1]:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-opacity="0.9"/>\n'
            f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-opacity="0.9"/>\n'
            f'<circle cx="{p1[0]:.1f}" cy="{p1[1]:.1f}" r="6" fill="{color}"/>\n'
            f'<circle cx="{p2[0]:.1f}" cy="{p2[1]:.1f}" r="8" fill="{color}"/>'
        )
    # 支点
    px, py = mapper.xy(0.0, 0.0)
    parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{_TEXT}"/>')

    # 图例
    th1a = math.degrees(run_a.states[0][0])
    th2a = math.degrees(run_a.states[0][2])
    dth = run_b.states[0][0] - run_a.states[0][0]
    ly = height - 88
    for i, (color, label) in enumerate((
        (COLOR_A, f"初值 A：θ₁ = {th1a:.4f}°，θ₂ = {th2a:.4f}°"),
        (COLOR_B, f"初值 B：θ₁ = {th1a + math.degrees(dth):.4f}°（Δθ₁ = {dth:.0e} rad）"),
    )):
        y = ly + i * 24
        parts.append(f'<line x1="60" y1="{y - 5}" x2="94" y2="{y - 5}" stroke="{color}" '
                     f'stroke-width="3" stroke-opacity="0.85"/>\n'
                     f'<text x="104" y="{y}" font-size="13" fill="{_TEXT}">{label}</text>')
    parts.append(f'<text x="60" y="{ly + 52}" font-size="12" fill="{_MUTED}">'
                 f'圆圈 = 终态两摆位置；细线 = 支点起算的杆。'
                 f'轨迹交叉处两色混色 —— 早期几乎重合，后期彻底分开。</text>')

    parts.append("</svg>\n")
    return "\n".join(parts)


# ---------------------------------------------------------------- 图 2：能量漂移

def energy_svg(pair: PairResult, width: int = 900, height: int = 470) -> str:
    """能量漂移曲线：ΔE(t) = E(t) - E₀，验证数值质量（应贴近 0）。"""
    run_a, run_b = pair.run_a, pair.run_b
    t_end = run_a.times[-1]
    drifts = []
    for run in (run_a, run_b):
        e0 = run.energies[0]
        drifts.extend(e - e0 for e in run.energies)
    m = max(abs(d) for d in drifts) if drifts else 1e-15
    m = max(m, 1e-15)

    px0, py0, px1, py1 = 86, 74, width - 34, height - 62
    parts = [_svg_open(width, height, "能量漂移 ΔE(t) = E(t) − E₀",
                       f"总能量应为运动常数；漂移越小说明数值质量越好 · "
                       f"E₀ = {run_a.energies[0]:.4f} J · RK4 dt = {run_a.dt * 1000:g} ms")]

    # 坐标轴与网格
    x_ticks = _nice_ticks(0.0, t_end, 6)
    y_ticks = _nice_ticks(-m, m, 5)
    for v in x_ticks:
        sx = px0 + (v - 0.0) / (t_end - 0.0) * (px1 - px0) if t_end > 0 else px0
        parts.append(f'<line x1="{sx:.1f}" y1="{py0}" x2="{sx:.1f}" y2="{py1}" '
                     f'stroke="{_GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{sx:.1f}" y="{py1 + 20}" text-anchor="middle" '
                     f'font-size="12" fill="{_MUTED}">{_fmt_tick(v)}</text>')
    for v in y_ticks:
        sy = py1 - (v + m) / (2 * m) * (py1 - py0)
        parts.append(f'<line x1="{px0}" y1="{sy:.1f}" x2="{px1}" y2="{sy:.1f}" '
                     f'stroke="{_GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{px0 - 8}" y="{sy + 4:.1f}" text-anchor="end" '
                     f'font-size="12" fill="{_MUTED}">{_fmt_tick(v)}</text>')

    # 零线
    zy = py1 - (0.0 + m) / (2 * m) * (py1 - py0)
    parts.append(f'<line x1="{px0}" y1="{zy:.1f}" x2="{px1}" y2="{zy:.1f}" '
                 f'stroke="#8e8e93" stroke-width="1.4" stroke-dasharray="5 4"/>')

    # 两条漂移曲线
    for run, color in ((run_a, COLOR_A), (run_b, COLOR_B)):
        e0 = run.energies[0]
        pairs = list(zip(run.times, run.energies))
        pts = [
            (
                px0 + (t / t_end) * (px1 - px0) if t_end > 0 else px0,
                py1 - ((e - e0) + m) / (2 * m) * (py1 - py0),
            )
            for t, e in _decimate(pairs)
        ]
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.4" '
                     f'stroke-linejoin="round" points="{_polyline(pts)}"/>')

    # 图例（含 max|ΔE| 数值）
    ly = py0 + 20
    for i, (color, run) in enumerate(((COLOR_A, run_a), (COLOR_B, run_b))):
        y = ly + i * 22
        parts.append(f'<line x1="{px1 - 250}" y1="{y - 5}" x2="{px1 - 222}" y2="{y - 5}" '
                     f'stroke="{color}" stroke-width="3"/>\n'
                     f'<text x="{px1 - 214}" y="{y}" font-size="12.5" fill="{_TEXT}">'
                     f'初值 {run.label}：max|ΔE| = {run.max_energy_drift():.2e} J</text>')

    # 轴标题
    parts.append(f'<text x="{(px0 + px1) // 2}" y="{py1 + 44}" text-anchor="middle" '
                 f'font-size="13" fill="{_TEXT}">时间 t (s)</text>')
    parts.append(f'<text x="26" y="{(py0 + py1) // 2}" text-anchor="middle" font-size="13" '
                 f'fill="{_TEXT}" transform="rotate(-90 26 {(py0 + py1) // 2})">ΔE (J)</text>')

    parts.append("</svg>\n")
    return "\n".join(parts)


# ---------------------------------------------------------------- 图 3：分岔距离对数曲线

def divergence_svg(pair: PairResult, threshold: float = 0.1, width: int = 900, height: int = 470) -> str:
    """分岔距离 log₁₀ d(t) 曲线：指数增长段近似直线 —— 混沌的经典指纹。"""
    t_end = pair.times[-1]
    pts_world = [(t, d) for t, d in zip(pair.times, pair.distances) if d > 0]
    init_d, fin_d = pair.initial_distance, pair.final_distance
    t_star = pair.bifurcation_time(threshold)

    sub = (f"初始距离 {init_d:.1e} → 终态 {fin_d:.1e}"
           + (f"（放大 ×{fin_d / init_d:.0e}）" if init_d > 0 else ""))
    parts = [_svg_open(width, height, "轨迹分岔距离随时间的对数曲线 log₁₀ d(t)", sub)]

    px0, py0, px1, py1 = 86, 74, width - 34, height - 62

    if not pts_world:
        parts.append(f'<text x="{width // 2}" y="{height // 2}" text-anchor="middle" '
                     f'font-size="15" fill="{_MUTED}">两组轨迹完全重合（距离恒为 0）</text>')
        parts.append("</svg>\n")
        return "\n".join(parts)

    logs = [math.log10(d) for _, d in pts_world]
    lo, hi = min(logs), max(logs)
    lo, hi = lo - 0.4, hi + 0.4
    if hi - lo < 1.0:
        mid = (hi + lo) / 2
        lo, hi = mid - 0.5, mid + 0.5

    def map_x(t: float) -> float:
        return px0 + (t / t_end) * (px1 - px0) if t_end > 0 else px0

    def map_y(v: float) -> float:
        return py1 - (v - lo) / (hi - lo) * (py1 - py0)

    # 整数刻度（对数轴上等距 = 等数量级）
    for e in range(math.ceil(lo), math.floor(hi) + 1):
        sy = map_y(e)
        parts.append(f'<line x1="{px0}" y1="{sy:.1f}" x2="{px1}" y2="{sy:.1f}" '
                     f'stroke="{_GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{px0 - 8}" y="{sy + 4:.1f}" text-anchor="end" '
                     f'font-size="12" fill="{_MUTED}">1e{e}</text>')
    for v in _nice_ticks(0.0, t_end, 6):
        sx = map_x(v)
        parts.append(f'<line x1="{sx:.1f}" y1="{py0}" x2="{sx:.1f}" y2="{py1}" '
                     f'stroke="{_GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{sx:.1f}" y="{py1 + 20}" text-anchor="middle" '
                     f'font-size="12" fill="{_MUTED}">{_fmt_tick(v)}</text>')

    # 阈值线
    if lo <= math.log10(threshold) <= hi:
        ty = map_y(math.log10(threshold))
        parts.append(f'<line x1="{px0}" y1="{ty:.1f}" x2="{px1}" y2="{ty:.1f}" '
                     f'stroke="#8e8e93" stroke-width="1.4" stroke-dasharray="5 4"/>\n'
                     f'<text x="{px1 - 6}" y="{ty - 7:.1f}" text-anchor="end" font-size="12" '
                     f'fill="{_MUTED}">阈值 {threshold:g}</text>')

    # 分岔时刻竖线
    if t_star is not None:
        sx = map_x(t_star)
        parts.append(f'<line x1="{sx:.1f}" y1="{py0}" x2="{sx:.1f}" y2="{py1}" '
                     f'stroke="{COLOR_A}" stroke-width="1.4" stroke-dasharray="4 4"/>\n'
                     f'<text x="{sx + 7:.1f}" y="{py0 + 16}" font-size="12.5" '
                     f'fill="{COLOR_A}">分岔 t* = {t_star:.2f} s</text>')

    # 主曲线
    pts = [(map_x(t), map_y(math.log10(d))) for t, d in _decimate(pts_world)]
    parts.append(f'<polyline fill="none" stroke="{COLOR_C}" stroke-width="2" '
                 f'stroke-linejoin="round" points="{_polyline(pts)}"/>')

    # 轴标题
    parts.append(f'<text x="{(px0 + px1) // 2}" y="{py1 + 44}" text-anchor="middle" '
                 f'font-size="13" fill="{_TEXT}">时间 t (s)</text>')
    parts.append(f'<text x="26" y="{(py0 + py1) // 2}" text-anchor="middle" font-size="13" '
                 f'fill="{_TEXT}" transform="rotate(-90 26 {(py0 + py1) // 2})">相空间距离 d(t)</text>')
    parts.append(f'<text x="{px0}" y="{py1 + 58}" font-size="12" fill="{_MUTED}">'
                 f'纵轴为对数刻度：近似直线段 = 指数发散（对初值的敏感依赖）。</text>')

    parts.append("</svg>\n")
    return "\n".join(parts)


# ---------------------------------------------------------------- 一键写出

def write_all(pair: PairResult, out_dir: str | Path, threshold: float = 0.1) -> list[Path]:
    """把三张 SVG 全部写进 out_dir，返回文件路径列表。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = [
        (TRAJECTORY_FILE, trajectory_svg(pair)),
        (ENERGY_FILE, energy_svg(pair)),
        (DIVERGENCE_FILE, divergence_svg(pair, threshold=threshold)),
    ]
    paths = []
    for name, content in files:
        p = out / name
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths
