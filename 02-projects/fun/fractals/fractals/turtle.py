"""海龟解释器：把 L-system 字符串解释为二维线段集合。

支持的命令（经典 turtle graphics 子集）：

======  =========================================================
``F``   前进一格并画线
``f``   前进一格不画线（移笔）
``+``   左转（逆时针）angle 度
``-``   右转（顺时针）angle 度
``[``   压栈：保存当前位置与朝向（分枝起点）
``]``   出栈：恢复位置与朝向（分枝结束）
======  =========================================================

其余符号（X、Y 等 L-system 辅助符）静默忽略——它们只服务于规则表。
坐标系采用数学惯例：y 轴向上、角度 0° 指向右方、90° 指向上方。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Segment", "TurtleError", "interpret", "normalize", "bounding_box"]


class TurtleError(ValueError):
    """海龟解释期错误（括号不匹配等）。"""


@dataclass(frozen=True)
class Segment:
    """一条从 (x1, y1) 到 (x2, y2) 的线段。"""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def translated(self, dx: float, dy: float) -> "Segment":
        return Segment(self.x1 + dx, self.y1 + dy, self.x2 + dx, self.y2 + dy)

    def scaled(self, k: float) -> "Segment":
        return Segment(self.x1 * k, self.y1 * k, self.x2 * k, self.y2 * k)


def interpret(
    code: str,
    *,
    angle: float = 90.0,
    step: float = 1.0,
    start: tuple[float, float] = (0.0, 0.0),
    heading: float = 90.0,
) -> list[Segment]:
    """把 L-system 字符串解释成线段列表。

    Parameters
    ----------
    code:
        L-system 展开后的字符串。
    angle:
        ``+`` / ``-`` 每次转动的度数。
    step:
        ``F`` / ``f`` 每次前进的长度单位。
    start:
        起点坐标。
    heading:
        起始朝向（度，0 = 右，90 = 上）。

    Raises
    ------
    TurtleError
        ``]`` 出现时栈为空，或字符串结束时栈不为空（分支不平衡）。
    """
    x, y = start
    heading_rad = math.radians(heading)
    turn = math.radians(angle)
    stack: list[tuple[float, float, float]] = []
    segments: list[Segment] = []

    for ch in code:
        if ch == "F":
            nx = x + step * math.cos(heading_rad)
            ny = y + step * math.sin(heading_rad)
            segments.append(Segment(x, y, nx, ny))
            x, y = nx, ny
        elif ch == "f":
            x += step * math.cos(heading_rad)
            y += step * math.sin(heading_rad)
        elif ch == "+":
            heading_rad += turn
        elif ch == "-":
            heading_rad -= turn
        elif ch == "[":
            stack.append((x, y, heading_rad))
        elif ch == "]":
            if not stack:
                raise TurtleError("分支栈下溢：']' 没有对应的 '['")
            x, y, heading_rad = stack.pop()
        else:
            # X / Y 等辅助符号：只参与重写，不产生几何动作
            continue

    if stack:
        raise TurtleError(f"分支栈不平衡：{len(stack)} 个 '[' 未闭合")
    return segments


def bounding_box(segments: list[Segment]) -> tuple[float, float, float, float]:
    """返回 (x_min, y_min, x_max, y_max)；空集合返回全 0。"""
    if not segments:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [s.x1 for s in segments] + [s.x2 for s in segments]
    ys = [s.y1 for s in segments] + [s.y2 for s in segments]
    return (min(xs), min(ys), max(xs), max(ys))


def normalize(
    segments: list[Segment],
    *,
    width: float = 1.0,
    height: float = 1.0,
    margin: float = 0.05,
) -> list[Segment]:
    """把线段集合等比缩放并平移进 [margin, 1-margin] 的目标框。

    保持纵横比、居中；空列表原样返回。坐标自动归一化的关键在于
    不同迭代数的 L-system 输出可以共用同一套渲染管线。
    """
    if not segments:
        return []
    if not 0 <= margin < 0.5:
        raise ValueError("margin 必须在 [0, 0.5) 内")
    x_min, y_min, x_max, y_max = bounding_box(segments)
    span_x = x_max - x_min
    span_y = y_max - y_min
    # 目标可用区域
    avail_w = width * (1.0 - 2 * margin)
    avail_h = height * (1.0 - 2 * margin)
    if span_x <= 0 and span_y <= 0:
        # 退化为一个点：整体平移到中心
        cx, cy = width / 2, height / 2
        return [s.translated(cx - x_min, cy - y_min) for s in segments]
    if span_x > 0 and span_y > 0:
        scale = min(avail_w / span_x, avail_h / span_y)
    elif span_x > 0:          # 水平退化线：只受宽度约束
        scale = avail_w / span_x
    else:                     # 纵向退化线：只受高度约束（否则无法填满画框）
        scale = avail_h / span_y
    # 居中：先缩放再平移
    off_x = (width - span_x * scale) / 2 - x_min * scale
    off_y = (height - span_y * scale) / 2 - y_min * scale
    return [
        Segment(s.x1 * scale + off_x, s.y1 * scale + off_y,
                s.x2 * scale + off_x, s.y2 * scale + off_y)
        for s in segments
    ]
