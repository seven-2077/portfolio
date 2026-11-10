"""pet.sprites — 各成长阶段的 ASCII 形象：多帧眨眼 + 心情变化 + 睡姿。

身体模板配 {eyes}/{mouth}/{decor} 占位：frame 奇偶交替眨眼，心情四档
（happy/normal/sad/miserable）换眼嘴装饰，sleeping 强制闭眼加 zZ。
"""

from __future__ import annotations

from dataclasses import dataclass

# 心情四档 → mood key
def mood_key(mood: float) -> str:
    if mood >= 75:
        return "happy"
    if mood >= 50:
        return "normal"
    if mood >= 25:
        return "sad"
    return "miserable"


@dataclass(frozen=True)
class _Look:
    body: tuple[str, ...]           # 含 {eyes} {mouth} {decor} 占位的模板
    eyes_open: dict[str, str]       # mood key → 睁眼画法
    eyes_shut: dict[str, str]       # mood key → 闭眼画法（眨眼帧）
    mouth: dict[str, str]           # mood key → 嘴
    decor: dict[str, str]           # mood key → 装饰行（爱心/雨滴/音符）


_EYES_SHUT = {"happy": "-   -", "normal": "-   -",
              "sad": "-   -", "miserable": "-   -"}

_LOOKS: dict[str, _Look] = {
    "egg": _Look(
        body=(
            "      ___    _    ",
            "   ,-'   `-' `-.  ",
            "  /  .-------.  \\ ",
            " |  ({eyes})  | ",
            " |    {mouth}     | ",
            "  \\  `-------'  / ",
            "   `-._______.-'  ",
            "     {decor}       ",
        ),
        eyes_open={"happy": "^ ^", "normal": "o o",
                   "sad": "o o", "miserable": "x x"},
        eyes_shut=_EYES_SHUT,
        mouth={"happy": "w", "normal": "-", "sad": "n", "miserable": "n"},
        decor={"happy": "~ ♪ ~", "normal": "  .  ",
               "sad": " , , ", "miserable": " . ' ."},
    ),
    "baby": _Look(
        body=(
            "    .-\"\"\"-.     ",
            "   /  {decor}  \\   ",
            "  |  {eyes}  |  ",
            "  |   {mouth}    |  ",
            "   \\  \\___/  /   ",
            "    '-------'    ",
            "     |__|__|     ",
        ),
        eyes_open={"happy": "^   ^", "normal": "o   o",
                   "sad": "o   o", "miserable": "x   x"},
        eyes_shut=_EYES_SHUT,
        mouth={"happy": "w", "normal": "u", "sad": "n", "miserable": "n"},
        decor={"happy": "*", "normal": "~", "sad": "~", "miserable": ","},
    ),
    "adult": _Look(
        body=(
            "    .-\"\"\"-.      ",
            "   / {decor}  \\    ",
            "  |  {eyes}  |   ",
            "  |   {mouth}     |   ",
            "  |  /|   |\\  |   ",
            "  (_/ |___| \\_)   ",
            "     _|___|_      ",
        ),
        eyes_open={"happy": "^   ^", "normal": "O   O",
                   "sad": "o   o", "miserable": "x   x"},
        eyes_shut=_EYES_SHUT,
        mouth={"happy": "w", "normal": "n", "sad": "n", "miserable": "n"},
        decor={"happy": "♪", "normal": "-", "sad": "·", "miserable": ","},
    ),
    "elder": _Look(
        body=(
            "    .-\"\"\"-.      ",
            "   / {decor}  \\    ",
            "  |  {eyes}  |   ",
            "  |  ~~~~~~~  |   ",
            "  |   {mouth}    |   ",
            "  (_/ |___| \\_)   ",
            "    =|_____|=     ",
            "      |_||_|      ",
        ),
        eyes_open={"happy": "^   ^", "normal": "O   O",
                   "sad": "~   ~", "miserable": "x   x"},
        eyes_shut=_EYES_SHUT,
        mouth={"happy": "w", "normal": "-", "sad": "n", "miserable": "n"},
        decor={"happy": "♪", "normal": "-", "sad": "·", "miserable": ","},
    ),
}


def get_sprite(stage_key: str, mood: float, frame: int = 0,
               sleeping: bool = False) -> str:
    """渲染一帧形象：frame 奇偶控制眨眼，sleeping 强制闭眼加 zZ。"""
    look = _LOOKS.get(stage_key, _LOOKS["baby"])
    mk = mood_key(mood)
    if sleeping:
        eyes, decor = look.eyes_shut[mk], "z Z z"
    else:
        eyes = look.eyes_open[mk] if frame % 2 == 0 else look.eyes_shut[mk]
        decor = look.decor[mk]
    mouth = look.mouth[mk]
    lines = [tpl.format(eyes=eyes, mouth=mouth, decor=decor)
             for tpl in look.body]
    width = max(len(line) for line in lines)   # 右缘对齐
    return "\n".join(line.ljust(width) for line in lines)
