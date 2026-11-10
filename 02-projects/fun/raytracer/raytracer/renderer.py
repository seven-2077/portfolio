"""渲染主循环：相机发线 → 求交 → 着色（递归反弹 + 阴影射线 + 天空渐变）。

Whitted 风格的着色流程（``Tracer.ray_color``）：

1. 反弹次数用完 → 返回黑色（递归上限，防止镜面隧道跑不完）；
2. 没打中任何物体 → 天空渐变（发光背景，也是画面里最亮的"光源"）；
3. 打中漫反射材质 → 算直射光：对每盏灯发一条**阴影射线**，
   被挡住就没有直射分量，加上环境光后乘反照率收工；
4. 打中金属/玻璃 → 按材质给的 (散射光线, 权重) 递归追踪，颜色按权重叠加。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from .camera import Camera
from .geometry import HittableList, T_MIN
from .vec import Ray, Vec3

__all__ = ["Light", "Scene", "Tracer", "render"]

_BLACK = Vec3(0.0, 0.0, 0.0)
_DEFAULT_RNG = random.Random(0x5EED)  # 不传 rng 时的兜底（保证结果可复现）


@dataclass
class Light:
    """方向光（太阳）：``direction`` 是**从物体指向光源**的单位向量。"""

    direction: Vec3
    color: Vec3 = Vec3(1.0, 1.0, 1.0)
    intensity: float = 1.0

    def __post_init__(self) -> None:
        self.direction = self.direction.normalized()


@dataclass
class Scene:
    """一个可渲染场景：世界 + 灯光 + 相机参数 + 天空配色。"""

    name: str
    world: HittableList
    look_from: Vec3
    look_at: Vec3
    vfov: float
    lights: List[Light] = field(default_factory=list)
    vup: Vec3 = Vec3(0.0, 1.0, 0.0)
    ambient: Vec3 = Vec3(0.14, 0.14, 0.17)
    sky_top: Vec3 = Vec3(0.45, 0.65, 1.0)
    sky_bottom: Vec3 = Vec3(1.0, 1.0, 1.0)

    def camera(self, aspect: float) -> Camera:
        return Camera(self.look_from, self.look_at, self.vup, self.vfov, aspect)


class Tracer:
    """着色器：给一条光线算出颜色（递归深度受 max_depth 限制）。"""

    __slots__ = ("world", "lights", "ambient", "sky_top", "sky_bottom", "max_depth")

    def __init__(
        self,
        world: HittableList,
        lights: Sequence[Light] = (),
        ambient: Vec3 = Vec3(0.14, 0.14, 0.17),
        sky_top: Vec3 = Vec3(0.45, 0.65, 1.0),
        sky_bottom: Vec3 = Vec3(1.0, 1.0, 1.0),
        max_depth: int = 8,
    ) -> None:
        self.world = world
        self.lights = tuple(lights)
        self.ambient = ambient
        self.sky_top = sky_top
        self.sky_bottom = sky_bottom
        self.max_depth = int(max_depth)

    # ---------- 背景 ----------

    def sky(self, direction: Vec3) -> Vec3:
        """垂直渐变天空：头顶是天顶色，地平线是地平色（t 线性插值）。"""
        t = 0.5 * (direction.normalized().y + 1.0)
        return self.sky_bottom * (1.0 - t) + self.sky_top * t

    # ---------- 阴影 ----------

    def occluded(self, origin: Vec3, direction: Vec3) -> bool:
        """阴影射线：沿 direction 探测是否撞上不透明物体。

        玻璃（``casts_shadow=False``）会被「穿过」，从它背后继续探测，
        所以玻璃球不会在地上留一块死黑的影子。
        """
        t_min = T_MIN
        while True:
            rec = self.world.hit(Ray(origin, direction), t_min, math.inf)
            if rec is None:
                return False
            if not rec.material.casts_shadow:
                t_min = rec.t + T_MIN  # 跳过透明体，继续往后问
                continue
            return True

    # ---------- 核心 ----------

    def ray_color(
        self,
        ray: Ray,
        depth: Optional[int] = None,
        rng: Optional[random.Random] = None,
    ) -> Vec3:
        """一条光线最终贡献的颜色（线性 RGB）。depth 剩 0 直接返回黑色。"""
        if depth is None:
            depth = self.max_depth
        if depth <= 0:
            return _BLACK  # 递归上限：镜面来回弹的光线在这里被截断

        rec = self.world.hit(ray, T_MIN, math.inf)
        if rec is None:
            return self.sky(ray.direction)

        material = rec.material
        color = _BLACK

        if material.uses_direct_light:
            total = self.ambient
            for light in self.lights:
                ndotl = rec.normal.dot(light.direction)  # Lambert 余弦因子
                if ndotl <= 0.0:
                    continue
                shadow_origin = rec.point + rec.normal * T_MIN
                if self.occluded(shadow_origin, light.direction):
                    continue  # 这盏灯被挡住了：只有环境光
                total = total + light.color * (light.intensity * ndotl)
            color = material.shade_direct(rec, total)

        if rng is None:
            rng = _DEFAULT_RNG
        for scattered, weight in material.scatter(ray, rec, rng):
            color = color + weight * self.ray_color(scattered, depth - 1, rng)
        return color


def render(
    scene: Scene,
    width: int,
    height: int,
    samples: int = 4,
    max_depth: int = 8,
    seed: int = 0,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[float]:
    """渲染整幅图，返回扁平的线性 RGB 像素列表（长度 width*height*3，行主序）。

    ``on_progress(done_rows, total_rows)`` 可选，每渲染完一行回调一次。
    """
    if width <= 0 or height <= 0:
        raise ValueError("width/height 必须是正数")
    if samples <= 0:
        raise ValueError("samples 必须是正数")

    camera = scene.camera(width / height)
    tracer = Tracer(
        scene.world,
        scene.lights,
        scene.ambient,
        scene.sky_top,
        scene.sky_bottom,
        max_depth,
    )
    rng = random.Random(seed)
    ray_color = tracer.ray_color          # 热路径上省一次属性查找
    ray_for_pixel = camera.ray_for_pixel
    inv_samples = 1.0 / samples

    framebuffer: List[float] = [0.0] * (width * height * 3)
    for y in range(height):
        row_base = y * width
        for x in range(width):
            r = g = b = 0.0
            for _ in range(samples):
                c = ray_color(ray_for_pixel(x, y, width, height, rng), None, rng)
                r += c.x
                g += c.y
                b += c.z
            i = 3 * (row_base + x)
            framebuffer[i] = r * inv_samples
            framebuffer[i + 1] = g * inv_samples
            framebuffer[i + 2] = b * inv_samples
        if on_progress is not None:
            on_progress(y + 1, height)
    return framebuffer
