#!/usr/bin/env python3
"""「涌现」实验室 demo：a) glider 终端 20 步动画 + 快照胶片；b) Gray-Scott 三组
feed/kill（斑点/条纹/蠕虫）各跑数百步 → 单图与三联图集输出到 output/。用法：python demo.py"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifelab import PRESETS, GameOfLife, GrayScott, get_pattern
from lifelab.viz import animate, field_atlas_svg, field_snapshot_svg, life_strip_svg

OUT = ROOT / "output"

GLIDER_STEPS = 20
GLIDER_FRAME_EVERY = 4
RD_SIZE = (96, 96)
RD_STEPS = 600
RD_SNAPSHOT_GENS = (200, 400, 600)


def demo_glider() -> list[Path]:
    """a) 滑翔机终端 20 步动画 + 关键时刻快照胶片。"""
    print("=" * 64)
    print("[a] glider 终端动画：20 步（4 代平移一格）")
    life = GameOfLife(40, 16)
    life.add(get_pattern("glider").cells_at((2, 2)))
    frames = animate(life, steps=GLIDER_STEPS, delay=0.08, clear=True)
    print(f"    共渲染 {frames} 帧，最终 population = {life.population}")

    # 关键时刻：gen 0,4,8,...,20 快照胶片
    sim = GameOfLife(40, 16)
    sim.add(get_pattern("glider").cells_at((2, 2)))
    snaps = sim.evolve(GLIDER_STEPS)[::GLIDER_FRAME_EVERY]
    svg = life_strip_svg(
        snaps,
        cell=6,
        labels=[f"gen {i * GLIDER_FRAME_EVERY}" for i in range(len(snaps))],
        title="glider: every 4 gens shifts (1,1)",
    )
    path = OUT / "life_glider_strip.svg"
    path.write_text(svg, encoding="utf-8")
    print(f"    快照胶片 → {path.relative_to(ROOT)}")
    return [path]


def demo_reaction_diffusion() -> list[Path]:
    """b) 三组 feed/kill 各跑数百步 → 单图 + 三联图集。"""
    print("=" * 64)
    print(f"[b] Gray-Scott 反应扩散：{len(PRESETS)} 组预设 × {RD_STEPS} 步，网格 {RD_SIZE[0]}x{RD_SIZE[1]}")
    w, h = RD_SIZE
    written: list[Path] = []
    panels: list[tuple[object, int, int, str]] = []

    for name, preset in PRESETS.items():
        sim = GrayScott.from_preset(w, h, name)
        snapshots: dict[int, tuple[float, ...]] = {}
        for target in RD_SNAPSHOT_GENS:
            sim.run(target - sim.generation)
            snapshots[target] = sim.field_v()
        st = sim.stats()
        print(
            f"    - {preset.label}({name}) F={preset.feed} k={preset.kill} "
            f"→ mean_v={st['mean_v']:.4f} edge={st['edge_density']:.4f} "
            f"占据率={st['occupied']:.1%}  [{preset.note}]"
        )
        for gen in RD_SNAPSHOT_GENS:
            panels.append(
                (snapshots[gen], w, h, f"{preset.label} F={preset.feed} k={preset.kill} · gen {gen}")
            )
        final = snapshots[RD_SNAPSHOT_GENS[-1]]
        svg = field_snapshot_svg(
            final,
            w,
            h,
            scale=5,
            mode="duo",
            label=f"{preset.label} (feed={preset.feed}, kill={preset.kill}) gen={RD_STEPS}",
        )
        path = OUT / f"rd_{name}.svg"
        path.write_text(svg, encoding="utf-8")
        written.append(path)
        print(f"      单图 → {path.relative_to(ROOT)}")

    atlas = field_atlas_svg(panels, columns=3, scale=3, mode="gray")
    atlas_path = OUT / "rd_atlas.svg"
    atlas_path.write_text(atlas, encoding="utf-8")
    written.append(atlas_path)
    print(f"    图集（3 预设 × 3 时刻）→ {atlas_path.relative_to(ROOT)}")
    return written


def main() -> int:
    OUT.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    paths = demo_glider() + demo_reaction_diffusion()
    print("=" * 64)
    print(f"完成，用时 {time.perf_counter() - t0:.1f}s，产物 {len(paths)} 个：")
    for p in paths:
        print(f"    {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
