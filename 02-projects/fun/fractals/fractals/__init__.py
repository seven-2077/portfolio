"""fractals —— 纯标准库分形生成器。

L-system 植物（字符串重写 + 海龟解释）与 Mandelbrot / Julia 集（逃逸时间 + 平滑着色）。
零第三方依赖，Python 3.10+，Windows 直接可跑。
"""
from .lsystem import LSystem
from .turtle import Segment, interpret, normalize
from .plants import Plant, PRESETS, make_lsystem
from .mandelbrot import Viewport, smooth_escape, mandelbrot_field, julia_field
from .render import GRADIENT, ascii_art, write_bmp
from .svg_turtle import segments_to_svg, write_svg

__all__ = [
    "LSystem",
    "Segment",
    "interpret",
    "normalize",
    "Plant",
    "PRESETS",
    "make_lsystem",
    "Viewport",
    "smooth_escape",
    "mandelbrot_field",
    "julia_field",
    "GRADIENT",
    "ascii_art",
    "write_bmp",
    "segments_to_svg",
    "write_svg",
]

__version__ = "1.0.0"
