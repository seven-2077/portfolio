"""virtual-pet — 拓麻歌子式终端电子宠物（纯标准库）。"""

from .engine import PetState, advance, feed, new_pet, play, sleep, wake

__all__ = ["PetState", "new_pet", "advance", "feed", "play", "sleep", "wake"]
__version__ = "0.1.0"
