#!/usr/bin/env python3
"""一键 demo：SVG 三件套 → output/，打印分岔时刻与能量漂移，末尾跑终端动画。

用法（项目根目录）：
    python demo.py                # 完整演示
    python demo.py --no-anim      # 跳过终端动画
    python demo.py --frames 120   # 动画帧数
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from pendulum import trace
from pendulum.ode import DEFAULT
from viz import ascii_anim, svg_out

OUT_DIR = Path(__file__).resolve().parent / "output"

# 演示初值：θ1 = 170°, θ2 = -120°, 静止释放 —— 近顶部不稳定平衡附近，混沌最快
BASE_STATE = (2.9670597283903604, 0.0, -2.0943951023931953, 0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="双摆混沌模拟器 demo")
    ap.add_argument("--t-end", type=float, default=10.0, help="仿真时长 (s)")
    ap.add_argument("--dt", type=float, default=1e-3, help="积分步长 (s)")
    ap.add_argument("--delta", type=float, default=1e-4, help="两组初值的角度差 (rad)")
    ap.add_argument("--threshold", type=float, default=0.1, help="分岔判定阈值（相空间距离）")
    ap.add_argument("--frames", type=int, default=60, help="终端动画帧数")
    ap.add_argument("--no-anim", action="store_true", help="跳过终端动画")
    args = ap.parse_args(argv)

    print("=" * 64)
    print(" 双摆混沌模拟器 · demo")
    print("=" * 64)

    # ---------- [1/3] 轨迹仿真 ----------
    print(f"\n[1/3] 两组初值同步仿真：Δθ₁ = {args.delta:.0e} rad，"
          f"T = {args.t_end:g} s，dt = {args.dt * 1000:g} ms")
    state_b = list(BASE_STATE)
    state_b[0] += args.delta
    t0 = time.perf_counter()
    pair = trace.run_pair(BASE_STATE, state_b, t_end=args.t_end, dt=args.dt, params=DEFAULT)
    elapsed = time.perf_counter() - t0
    print(f"      初值 A: θ₁ = 170° (2.967060 rad)，θ₂ = -120° (-2.094395 rad)，静止释放")
    print(f"      初值 B: 同上，仅 θ₁ + {args.delta:.0e} rad")
    print(f"      耗时 {elapsed:.2f}s（纯 Python RK4，{len(pair.times)} 步 × 2 组）")

    t_star = pair.bifurcation_time(args.threshold)
    if t_star is not None:
        print(f"\n  ★ 分岔时刻：t = {t_star:.2f} s"
              f"（相空间距离首次超过 {args.threshold:g}）")
    else:
        print(f"\n  · 到 t = {args.t_end:g} s 仍未超过阈值 {args.threshold:g}"
              f"（可加大 --t-end 或 --delta）")
    print(f"    距离演化：{pair.initial_distance:.1e} → {pair.final_distance:.1e}"
          f"（放大 ×{pair.final_distance / max(pair.initial_distance, 1e-30):.0e}）")

    print("\n  能量漂移（数值质量体检）：")
    for run in (pair.run_a, pair.run_b):
        print(f"    初值 {run.label}：max|ΔE| = {run.max_energy_drift():.3e} J，"
              f"相对漂移 = {run.relative_energy_drift():.3e}"
              f"（E₀ = {run.energies[0]:.4f} J）")

    # ---------- [2/3] SVG 输出 ----------
    print(f"\n[2/3] 生成 SVG → {OUT_DIR}")
    paths = svg_out.write_all(pair, OUT_DIR, threshold=args.threshold)
    for p in paths:
        print(f"    ✓ {p.name}  ({p.stat().st_size / 1024:.1f} KB)")

    # ---------- [3/3] 终端动画 ----------
    if args.no_anim:
        print("\n[3/3] 已跳过终端动画（--no-anim）")
    else:
        print(f"\n[3/3] 终端 ASCII 动画演示（{args.frames} 帧，"
              f"{'实时 · q/Esc 退出' if sys.stdout.isatty() else '非交互终端 → 抽样帧'}）")
        shown = ascii_anim.run_animation(BASE_STATE, frames=args.frames, params=DEFAULT)
        print(f"    渲染 {shown} 帧。")

    print("\n完成。产物见 output/ —— 打开 trajectory_compare.svg 看两色轨迹分道扬镳。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
