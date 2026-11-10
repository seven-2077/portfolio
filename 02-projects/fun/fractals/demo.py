"""一键生成全部演示产物到 output/。

    python demo.py

产出：
  output/fern.svg            蕨类（L-system 4 代展开）
  output/koch_snowflake.svg  Koch 雪花（4 代）
  output/mandelbrot.bmp      Mandelbrot 集 24bpp 位图
  output/julia_*.bmp         4 个预设 c 的 Julia 集
  output/julia_atlas.bmp     四联图集（2×2 拼版）
同时在终端打印一幅 Mandelbrot ASCII 字符画。
"""
from __future__ import annotations

import os
import time

from fractals import (
    PRESETS,
    Viewport,
    ascii_art,
    interpret,
    julia_field,
    mandelbrot_field,
    write_bmp,
    write_svg,
)
from fractals.render import RGB, field_to_pixels, ocean

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "output")

# Julia 集「c 参数扫描」四个预设：
# 枝晶尘（近 M 边界）→ 兔子（连通·黑内核）→ 螺旋尘 → 旋涡星系（黑内核）
JULIA_PRESETS: tuple[tuple[str, complex], ...] = (
    ("dendrite", complex(-0.7, 0.27015)),
    ("rabbit", complex(-0.123, 0.745)),
    ("spiral", complex(0.285, 0.01)),
    ("galaxy", complex(-0.1592, -1.0317)),
)


def _elapsed(t0: float) -> str:
    return f"{time.perf_counter() - t0:.2f}s"


def make_lsystem_svg(name: str, out_name: str, *, width: int = 760,
                     height: int = 900) -> str:
    """展开预置植物 → 海龟解释 → SVG（内部自动归一化）。"""
    plant = PRESETS[name]
    system = plant.lsystem(seed=42)
    code = system.iterate(plant.iterations)
    segments = interpret(code, angle=plant.angle)
    path = os.path.join(OUTPUT_DIR, out_name)
    write_svg(path, segments, width=width, height=height,
              stroke="#175c2e" if name == "fern" else "#0b3d91")
    print(f"  [lsystem] {name:14s} {len(code):>7} 符号 → {len(segments):>5} 线段"
          f" → {out_name}")
    return path


def make_mandelbrot_bmp(out_name: str = "mandelbrot.bmp",
                        width: int = 800, height: int = 600) -> str:
    """经典视口的 Mandelbrot 集 → 24bpp BMP。"""
    vp = Viewport.centered(-0.75, 0.0, 1.75, 1.75 * height / width)
    field = mandelbrot_field(width, height, vp, max_iter=300)
    pixels = field_to_pixels(field, 300, palette=ocean)
    path = os.path.join(OUTPUT_DIR, out_name)
    write_bmp(path, width, height, pixels)
    print(f"  [mandelbrot] {width}x{height} max_iter=300 → {out_name}")
    return path


def make_julia_atlas(tile: int = 480) -> list[str]:
    """4 个预设 c：各自单图 + 2×2 图集，全部 24bpp BMP。"""
    paths: list[str] = []
    max_iter = 260
    vp = Viewport.centered(0.0, 0.0, 1.75)
    tiles: list[list[list[RGB]]] = []

    for idx, (name, c) in enumerate(JULIA_PRESETS):
        field = julia_field(tile, tile, c, vp, max_iter=max_iter)
        pixels = field_to_pixels(field, max_iter, palette=ocean)
        single = os.path.join(OUTPUT_DIR, f"julia_{idx + 1}_{name}.bmp")
        write_bmp(single, tile, tile, pixels)
        paths.append(single)
        tiles.append(pixels)
        print(f"  [julia] c={c} ({name:8s}) {tile}x{tile} → "
              f"julia_{idx + 1}_{name}.bmp")

    # 2×2 拼版：左上 dendrite、右上 rabbit、左下 spiral、右下 galaxy
    top = [tiles[0][r] + tiles[1][r] for r in range(tile)]
    bottom = [tiles[2][r] + tiles[3][r] for r in range(tile)]
    atlas_pixels = top + bottom
    atlas = os.path.join(OUTPUT_DIR, "julia_atlas.bmp")
    write_bmp(atlas, tile * 2, tile * 2, atlas_pixels)
    paths.append(atlas)
    print(f"  [julia] 2x2 图集 {tile * 2}x{tile * 2} → julia_atlas.bmp")
    return paths


def print_ascii_mandelbrot(width: int = 76, height: int = 34) -> None:
    """终端字符画：复平面视口可配，亮度字符渐变表渲染。

    终端字符约 2:1（高:宽），故虚轴跨度按 2*rows/cols 折算保证不变形。
    """
    vp = Viewport.centered(-0.4, 0.0, 1.6, 1.6 * height / width * 2.0)
    field = mandelbrot_field(width, height, vp, max_iter=160)
    print("\nMandelbrot @ 终端（ASCII 亮度渐变，白底反色）:")
    print(ascii_art(field, 160, invert=True))


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"输出目录: {OUTPUT_DIR}\n")
    t0 = time.perf_counter()

    print("L-system 植物：")
    fern_svg = make_lsystem_svg("fern", "fern.svg")
    koch_svg = make_lsystem_svg("koch_snowflake", "koch_snowflake.svg",
                                width=860, height=860)

    print("逃逸时间分形：")
    mandel_bmp = make_mandelbrot_bmp()
    julia_paths = make_julia_atlas()

    print_ascii_mandelbrot()

    files = [fern_svg, koch_svg, mandel_bmp, *julia_paths]
    print(f"\n完成：{len(files)} 个文件写入 output/，耗时 {_elapsed(t0)}")
    for f in files:
        print(f"  - {os.path.relpath(f, HERE)}  ({os.path.getsize(f):,} bytes)")


if __name__ == "__main__":
    main()
