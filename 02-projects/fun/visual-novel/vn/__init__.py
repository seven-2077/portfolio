"""vn —— 纯标准库的终端文字冒险 / 视觉小说引擎（引擎与剧本分离）。

用法：``Script.from_file("story/x.vn")`` -> ``Engine(script).run()`` 返回结局名。
完整教程见 README。
"""

from .script import Script, ScriptError, parse_script
from .state import HistoryEntry, SaveError, State, StateError
from .render import Renderer, KeyPoller, strip_ansi
from .engine import Engine, EngineConfig, EngineError, DEFAULT_ENDING

__version__ = "1.0.0"
__all__ = [
    "Script", "ScriptError", "parse_script",
    "State", "StateError", "SaveError", "HistoryEntry",
    "Renderer", "KeyPoller", "strip_ansi",
    "Engine", "EngineConfig", "EngineError", "DEFAULT_ENDING",
]
