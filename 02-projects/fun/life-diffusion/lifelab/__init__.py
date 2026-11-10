"""lifelab —— 涌现实验室：康威生命游戏 × Gray-Scott 反应扩散。只写局部规则，全局结构凭空涌现。"""

from .game_of_life import GameOfLife
from .grey_scott import PRESETS, GrayScott, RDPreset
from .patterns import PATTERNS, Pattern, get_pattern

__version__ = "0.1.0"
__all__ = ["GameOfLife", "GrayScott", "PRESETS", "RDPreset", "PATTERNS",
           "Pattern", "get_pattern", "__version__"]
