"""内置场景：经典三球 + 彩色玻璃球阵。

每个场景 = 世界（几何 + 材质）+ 灯光 + 相机参数 + 天空配色，
交给 ``raytracer.renderer.render`` 就能出图。
"""

from __future__ import annotations

from raytracer.geometry import HittableList, Plane, Sphere
from raytracer.materials import Glass, Lambert, Metal
from raytracer.renderer import Light, Scene
from raytracer.vec import Vec3

__all__ = ["classic_three", "glass_grid", "SCENES"]


def classic_three() -> Scene:
    """经典三球：漫反射 + 玻璃 + 金属，站在无限平地上。"""
    world = HittableList([
        Plane(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Lambert((0.80, 0.80, 0.84))),
        Sphere(Vec3(-1.15, 0.60, 0.10), 0.60, Lambert((0.92, 0.36, 0.30))),   # 红色漫反射
        Sphere(Vec3(0.0, 0.70, -0.25), 0.70, Glass(ior=1.50)),                # 玻璃
        Sphere(Vec3(1.25, 0.60, 0.35), 0.60, Metal((0.95, 0.93, 0.88), 0.10)),  # 微粗糙金属
    ])
    return Scene(
        name="classic —— 经典三球（漫反射 + 玻璃 + 金属）",
        world=world,
        look_from=Vec3(0.0, 1.35, 3.9),
        look_at=Vec3(0.0, 0.62, 0.0),
        vfov=40.0,
        lights=[Light(Vec3(-0.45, 1.0, 0.35), Vec3(1.0, 0.97, 0.90), 1.2)],
        ambient=Vec3(0.16, 0.17, 0.22),
        sky_top=Vec3(0.42, 0.62, 0.98),
        sky_bottom=Vec3(0.98, 0.99, 1.0),
    )


def glass_grid() -> Scene:
    """彩色玻璃球阵：8 颗不同染色的玻璃球围着中心一颗金金属球。"""
    tints = [
        (0.96, 0.70, 0.70), (0.70, 0.86, 0.97), (0.74, 0.94, 0.78),
        (0.97, 0.90, 0.66), (0.86, 0.74, 0.96), (0.68, 0.92, 0.92),
        (0.97, 0.78, 0.90), (0.88, 0.88, 0.72),
    ]
    objects = [Plane(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Lambert((0.86, 0.84, 0.80)))]
    tint_index = 0
    for row in (-1, 0, 1):
        for col in (-1, 0, 1):
            center = Vec3(col * 1.2, 0.5, row * 1.2)
            if row == 0 and col == 0:
                objects.append(Sphere(center, 0.5, Metal((1.0, 0.78, 0.34), roughness=0.05)))
            else:
                ior = 1.45 + 0.03 * (tint_index % 3)  # 折射率微差，色散的"影子"
                objects.append(Sphere(center, 0.5, Glass(ior=ior, tint=tints[tint_index])))
                tint_index += 1
    return Scene(
        name="grid —— 彩色玻璃球阵（8 玻璃 + 1 金球）",
        world=HittableList(objects),
        look_from=Vec3(0.0, 3.6, 5.6),
        look_at=Vec3(0.0, 0.4, 0.0),
        vfov=42.0,
        lights=[Light(Vec3(0.5, 1.0, -0.25), Vec3(1.0, 0.96, 0.88), 1.15)],
        ambient=Vec3(0.15, 0.16, 0.21),
        sky_top=Vec3(0.48, 0.66, 0.96),
        sky_bottom=Vec3(1.0, 0.96, 0.90),
    )


SCENES = {
    "classic": classic_three,
    "grid": glass_grid,
}
