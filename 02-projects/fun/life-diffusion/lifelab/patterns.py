"""预置图案库：经典 Gosper 字符表示 + 图案元信息。

四个必收图案：
    glider                 滑翔机（4 步平移一格）
    blinker                蜂鸣器（周期 2 的最简振荡器）
    pulsar                 脉冲星（周期 3，48 格）
    gosper_glider_gun      Gosper 滑翔机枪（1970，周期 30 出弹）
"""

from __future__ import annotations

from dataclasses import dataclass

from .game_of_life import LIVE_CHARS, GameOfLife

# 经典 Gosper 字符表示（每行显式拼接，长度即枪体 36 列）
GLIDER = ".O.\n..O\nOOO"
BLINKER = "OOO"
PULSAR = "\n".join(
    [
        "..OOO...OOO..",
        ".............",
        "O....O.O....O",
        "O....O.O....O",
        "O....O.O....O",
        "..OOO...OOO..",
        ".............",
        "..OOO...OOO..",
        "O....O.O....O",
        "O....O.O....O",
        "O....O.O....O",
        ".............",
        "..OOO...OOO..",
    ]
)
GOSPER_GLIDER_GUN = "\n".join(
    [
        "." * 24 + "O" + "." * 11,
        "." * 22 + "O.O" + "." * 11,
        "." * 12 + "OO" + "." * 6 + "OO" + "." * 12 + "OO",
        "." * 11 + "O" + "." * 3 + "O" + "." * 4 + "OO" + "." * 12 + "OO",
        "OO" + "." * 8 + "O" + "." * 5 + "O" + "." * 3 + "OO" + "." * 14,
        "OO" + "." * 8 + "O" + "." * 3 + "O" + "." + "OO" + "." * 4 + "O" + "." + "O" + "." * 11,
        "." * 10 + "O" + "." * 5 + "O" + "." * 7 + "O" + "." * 11,
        "." * 11 + "O" + "." * 3 + "O" + "." * 20,
        "." * 12 + "OO" + "." * 22,
    ]
)


@dataclass(frozen=True)
class Pattern:
    """图案元信息：文本之外还带分类、周期、发现者等履历。"""

    name: str
    text: str
    category: str  # spaceship / oscillator / gun
    period: int  # 振荡周期（枪为出弹周期）
    discovered_by: str
    year: int
    description: str
    translates: bool = False
    translation: tuple[int, int] | None = None

    @property
    def rows(self) -> tuple[str, ...]:
        return tuple(r for r in (ln.strip() for ln in self.text.splitlines()) if r)

    @property
    def width(self) -> int:
        return max(len(r) for r in self.rows)

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def cells(self) -> frozenset[tuple[int, int]]:
        """图案在自身局部坐标系中的活细胞集合。"""
        out: set[tuple[int, int]] = set()
        for y, row in enumerate(self.rows):
            for x, ch in enumerate(row):
                if ch in LIVE_CHARS:
                    out.add((x, y))
        return frozenset(out)

    def cells_at(self, origin: tuple[int, int] = (0, 0)) -> frozenset[tuple[int, int]]:
        """平移到指定原点后的活细胞集合。"""
        ox, oy = origin
        return frozenset((x + ox, y + oy) for x, y in self.cells)

    def to_game(
        self,
        width: int | None = None,
        height: int | None = None,
        origin: tuple[int, int] = (0, 0),
        *,
        wrap: bool = False,
    ) -> GameOfLife:
        """落到网格上；缺省尺寸 = 图案包围盒 + 原点偏移。"""
        ox, oy = origin
        w = width if width is not None else ox + self.width
        h = height if height is not None else oy + self.height
        return GameOfLife(w, h, self.cells_at(origin), wrap=wrap)


def _pattern(**kwargs: object) -> Pattern:
    p = Pattern(**kwargs)  # type: ignore[arg-type]
    PATTERNS[p.name] = p
    return p


PATTERNS: dict[str, Pattern] = {}

_pattern(name="glider", text=GLIDER, category="spaceship", period=4,
         discovered_by="Richard K. Guy", year=1969, translates=True, translation=(1, 1),
         description="最小的滑翔机：每 4 代向东南平移 (1,1)，把信息带出原地。")
_pattern(name="blinker", text=BLINKER, category="oscillator", period=2,
         discovered_by="John Horton Conway", year=1970,
         description="最简振荡器：横竖两态每代互换，2 代一循环。")
_pattern(name="pulsar", text=PULSAR, category="oscillator", period=3,
         discovered_by="John Horton Conway", year=1970,
         description="第四大常见振荡器：48 格、相位 48/56/72，3 代一循环（中间相外扩 1 格）。")
_pattern(name="gosper_glider_gun", text=GOSPER_GLIDER_GUN, category="gun", period=30,
         discovered_by="Bill Gosper", year=1970,
         description="第一台枪：36 格、每 30 代吐出一架滑翔机，证明 Life 无上界增长。")

# 别名（归一化后索引：小写、去空格/下划线/连字符）
_ALIASES = {
    "gun": "gosper_glider_gun",
    "gospergun": "gosper_glider_gun",
    "glidergun": "gosper_glider_gun",
    "滑翔机": "glider",
    "蜂鸣器": "blinker",
    "闪灯": "blinker",
    "脉冲星": "pulsar",
    "枪": "gosper_glider_gun",
}


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


_INDEX = {_norm(k): k for k in PATTERNS}
_INDEX.update({_norm(alias): target for alias, target in _ALIASES.items()})


def get_pattern(name: str) -> Pattern:
    """按名称/别名取图案；未收录抛 KeyError 并列出可用项。"""
    key = _INDEX.get(_norm(name))
    if key is None:
        known = ", ".join(sorted(PATTERNS))
        raise KeyError(f"未收录图案 {name!r}，可用：{known}")
    return PATTERNS[key]
