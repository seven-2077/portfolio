"""终端五子棋 AI —— Minimax + Alpha-Beta 剪枝（纯标准库，零依赖）。

模块结构:
    board     棋盘状态、落子/提子、候选走法生成
    rules     五连胜负判定、平局判定
    evaluate  模式评分（棋型启发式）
    search    Minimax(Negamax) + Alpha-Beta + 迭代加深
    cli       终端人机对战
    selfplay  AI vs AI 自对弈，输出文本棋谱
"""

from .board import BLACK, EMPTY, SIZE, WHITE, Board, opponent

__version__ = "1.0.0"
__all__ = ["Board", "BLACK", "WHITE", "EMPTY", "SIZE", "opponent"]
