"""raytracer —— 纯标准库的迷你光线追踪渲染器（零依赖，Python 3.10+）。"""

from .bmp import write_bmp
from .camera import Camera
from .geometry import HitRecord, HittableList, Plane, Sphere, T_MIN
from .materials import Glass, Lambert, Material, Metal
from .renderer import Light, Scene, Tracer, render
from .vec import Ray, Vec3, dot, cross, lerp, reflect, refract

__version__ = "0.1.0"

__all__ = [
    "Vec3", "Ray", "dot", "cross", "lerp", "reflect", "refract",
    "HitRecord", "Sphere", "Plane", "HittableList", "T_MIN",
    "Material", "Lambert", "Metal", "Glass",
    "Camera", "Light", "Scene", "Tracer", "render", "write_bmp",
    "__version__",
]
