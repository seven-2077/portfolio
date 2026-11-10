"""关卡定义（JSON 加载）与结构合法性校验。

坐标系：y 轴向下，(0,0) 为世界左上角；ground_y 为地面线；
方块用中心点 (x, y) + 宽高 (w, h) 描述。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from physics.collision import Box
from physics.structure import MATERIALS
from physics.verlet import Particle

LEVELS_DIR = Path(__file__).resolve().parent.parent / "levels"
MAX_BLOCKS = 60
PROJ_R = 0.55


class LevelError(ValueError):
    """关卡不合法（错误信息列出全部问题）。"""


@dataclass
class BlockDef:
    x: float
    y: float
    w: float
    h: float
    material: str


@dataclass
class LevelSpec:
    index: int
    name: str
    world_w: float
    world_h: float
    ground_y: float
    gravity: float
    sling: tuple[float, float]
    ammo: int
    blocks: list[BlockDef] = field(default_factory=list)

    @property
    def par(self) -> int:
        """最低完成线：4 块折算 1 发的基准。"""
        return max(1, round(self.total_blocks / 4))

    @property
    def total_blocks(self) -> int:
        return len(self.blocks)


def make_spec(
    blocks: list[BlockDef],
    *,
    index: int = 0,
    name: str = "test",
    world_w: float = 96.0,
    world_h: float = 32.0,
    ground_y: float = 28.0,
    gravity: float = 30.0,
    sling: tuple[float, float] = (10.0, 24.0),
    ammo: int = 3,
) -> LevelSpec:
    """代码内构造关卡（测试 / 快速原型用），同样要过 validate()。"""
    return LevelSpec(index, name, world_w, world_h, ground_y, gravity, sling, ammo, blocks)


def validate(data: dict, *, index: int = 0) -> list[str]:
    """合法性校验，返回错误列表（空 = 合法）。"""
    errs: list[str] = []
    try:
        name = data["name"]
        world = data["world"]
        w, h = float(world["width"]), float(world["height"])
        ground_y = float(data["ground_y"])
        gravity = float(world.get("gravity", 30))
        sx, sy = (float(v) for v in data["sling"])
        ammo = int(data["ammo"])
        raw_blocks = data["blocks"]
    except (KeyError, TypeError, ValueError) as e:
        return [f"字段缺失或类型错误: {e}"]

    if not isinstance(name, str) or not name:
        errs.append("name 必须是非空字符串")
    if w < 40 or h < 20:
        errs.append("世界尺寸过小（width>=40, height>=20）")
    if not (0 < gravity <= 200):
        errs.append("gravity 必须在 (0, 200] 内")
    if not (0 < ground_y < h):
        errs.append("ground_y 必须在 (0, height) 内")
    if not (0 < sx < w and 0 < sy < ground_y):
        errs.append("弹弓锚点必须在世界内且高于地面")
    if not (1 <= ammo <= 9):
        errs.append("ammo 必须在 1..9")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        errs.append("blocks 必须是非空列表")
        return errs
    if len(raw_blocks) > MAX_BLOCKS:
        errs.append(f"方块数量超上限 {MAX_BLOCKS}")

    defs: list[BlockDef] = []
    for i, b in enumerate(raw_blocks):
        try:
            bd = BlockDef(
                float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"]),
                str(b["material"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            errs.append(f"blocks[{i}] 字段错误: {e}")
            continue
        if bd.material not in MATERIALS:
            errs.append(f"blocks[{i}] 未知材质 {bd.material!r}")
            continue
        if bd.w <= 0 or bd.h <= 0 or bd.w > 20 or bd.h > 20:
            errs.append(f"blocks[{i}] 尺寸非法 {bd.w}x{bd.h}")
            continue
        if bd.x - bd.w / 2 < -1e-6 or bd.x + bd.w / 2 > w + 1e-6:
            errs.append(f"blocks[{i}] 超出世界左右边界")
        if bd.y - bd.h / 2 < -1e-6 or bd.y + bd.h / 2 > ground_y + 1e-6:
            errs.append(f"blocks[{i}] 越过地面线或世界顶部")
        defs.append(bd)

    # 两两重叠检测
    for i in range(len(defs)):
        a = _as_box(defs[i])
        for j in range(i + 1, len(defs)):
            b = _as_box(defs[j])
            if _overlap(a, b) > 1e-6:
                errs.append(f"blocks[{i}] 与 blocks[{j}] 重叠")

    # 支撑检测：每个方块底边须贴地或贴某方块顶边
    for i, bd in enumerate(defs):
        box = _as_box(bd)
        if abs(box.bottom - ground_y) <= 1e-6:
            continue
        ok = False
        for j, other in enumerate(defs):
            if i == j:
                continue
            ob = _as_box(other)
            if abs(ob.top - box.bottom) <= 1e-6 and _overlap_x(box, ob) > 1e-6:
                ok = True
                break
        if not ok:
            errs.append(f"blocks[{i}] 悬空：底边既不贴地也不贴其它方块")

    # 锚点（也是弹丸出生点）不能贴近方块
    for i, bd in enumerate(defs):
        box = _as_box(bd)
        if (
            box.left - PROJ_R < sx < box.right + PROJ_R
            and box.top - PROJ_R < sy < box.bottom + PROJ_R
        ):
            errs.append(f"弹弓锚点/出生点与 blocks[{i}] 冲突")
            break
    return errs


def _as_box(bd: BlockDef) -> Box:
    p = Particle(bd.x, bd.y, bd.x, bd.y, 0.0)
    return Box(p, bd.w / 2, bd.h / 2)


def _overlap(a: Box, b: Box) -> float:
    return min(_overlap_x(a, b), min(a.bottom, b.bottom) - max(a.top, b.top))


def _overlap_x(a: Box, b: Box) -> float:
    return min(a.right, b.right) - max(a.left, b.left)


def load(path: str | Path | None = None, *, index: int | None = None) -> LevelSpec:
    """加载关卡 JSON 并校验；失败抛 LevelError。"""
    if path is None:
        if index is None:
            raise ValueError("需要 path 或 index")
        path = LEVELS_DIR / f"level{index}.json"
    path = Path(path)
    if not path.exists():
        raise LevelError(f"关卡文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LevelError(f"JSON 解析失败: {e}") from e

    if index is None:
        digits = "".join(ch for ch in path.stem if ch.isdigit())
        index = int(digits) if digits else 0
    errs = validate(data, index=index)
    if errs:
        raise LevelError(f"关卡 {path.name} 不合法:\n  - " + "\n  - ".join(errs))

    blocks = [
        BlockDef(
            float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"]),
            str(b["material"]),
        )
        for b in data["blocks"]
    ]
    return LevelSpec(
        index=index,
        name=str(data["name"]),
        world_w=float(data["world"]["width"]),
        world_h=float(data["world"]["height"]),
        ground_y=float(data["ground_y"]),
        gravity=float(data["world"].get("gravity", 30)),
        sling=(float(data["sling"][0]), float(data["sling"][1])),
        ammo=int(data["ammo"]),
        blocks=blocks,
    )


def load_all() -> list[LevelSpec]:
    """按文件名顺序加载全部关卡。"""
    files = sorted(LEVELS_DIR.glob("level*.json"))
    if not files:
        raise LevelError(f"未找到关卡: {LEVELS_DIR}")
    return [load(f) for f in files]
