#!/usr/bin/env python3
"""渲染演示：跑场景、计时、把 BMP 落进 output/。

用法（在项目根目录）::

    python demo.py                      # 默认渲染 3 张
    python demo.py --scene classic      # 只渲染经典三球
    python demo.py --width 640 --samples 16   # 更高画质（更慢）

产物全部写在项目内 ``output/``，双击即可用 Windows 照片查看器打开。
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from raytracer.bmp import write_bmp
from raytracer.renderer import render

import scenes

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _progress(done: int, total: int) -> None:
    pct = done * 100 // total
    if pct != getattr(_progress, "_last", -1):  # 只在跨过新百分比时刷新，避免刷屏
        _progress._last = pct
        sys.stdout.write(f"\r      进度 {pct:3d}%（{done}/{total} 行）")
        sys.stdout.flush()
    if done == total:
        _progress._last = -1
        sys.stdout.write("\n")


def build_jobs(args) -> list:
    """返回 [(场景键, 标签, 宽, 高, 采样数), ...]。"""
    height = max(1, round(args.width * 9 / 16))
    jobs = []
    if args.scene in ("classic", "all"):
        jobs.append(("classic", "classic", args.width, height, args.samples))
    if args.scene in ("grid", "all"):
        jobs.append(("grid", "grid", args.width, height, args.samples))
    if args.scene == "all" and not args.no_hero:
        # 主图：更高分辨率 + 双倍采样，第一眼的「哇」靠它
        hero_w = max(args.width, 640)
        jobs.append(("classic", "classic_hero", hero_w, round(hero_w * 9 / 16), args.samples * 2))
    return jobs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="纯 Python 光线追踪渲染演示")
    parser.add_argument("--scene", choices=["classic", "grid", "all"], default="all",
                        help="渲染哪个场景（默认 all = 两场景 + 一张主图）")
    parser.add_argument("--width", type=int, default=480, help="预览图宽度（默认 480）")
    parser.add_argument("--samples", type=int, default=4, help="每像素采样数（默认 4）")
    parser.add_argument("--depth", type=int, default=8, help="递归反弹上限（默认 8）")
    parser.add_argument("--seed", type=int, default=0, help="随机种子（同种子结果可复现）")
    parser.add_argument("--no-hero", action="store_true", help="不渲染高质量主图")
    args = parser.parse_args(argv)

    jobs = build_jobs(args)
    if not jobs:
        parser.error("没有可渲染的场景")

    print("=" * 58)
    print(" 纯 Python 光线追踪 · 渲染演示（零依赖，stdlib only）")
    print("=" * 58)

    os.makedirs(OUT_DIR, exist_ok=True)
    total_start = time.perf_counter()
    for index, (scene_key, label, width, height, samples) in enumerate(jobs, 1):
        scene = scenes.SCENES[scene_key]()
        filename = f"{label}_{width}x{height}.bmp"
        path = os.path.join(OUT_DIR, filename)
        print(f"[{index}/{len(jobs)}] {scene.name}")
        print(f"      分辨率 {width}x{height} · 采样 {samples} spp · 反弹上限 {args.depth}")
        start = time.perf_counter()
        framebuffer = render(
            scene, width, height,
            samples=samples, max_depth=args.depth, seed=args.seed,
            on_progress=_progress,
        )
        elapsed = time.perf_counter() - start
        write_bmp(path, width, height, framebuffer)
        kpixels = width * height / 1000.0
        print(f"      耗时 {elapsed:.1f}s（{kpixels / elapsed:.1f} kpx/s）→ output/{filename}")

    total = time.perf_counter() - total_start
    print("-" * 58)
    print(f"{len(jobs)} 张图完成，总耗时 {total:.1f}s，均在 output/ 目录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
