"""模式评分函数：棋型启发式（威胁等级 → 分值）。

棋型记号（对某一方而言）：1 = 己方棋子，0 = 空点，2 = 对方棋子/边界。
每种棋型的威胁等级（SCORES 表，数值本身就是注释）：

    five       10_000_000  活五/五连   —— 已经赢了，终局信号
    open_four   1_000_000  活四        —— 双杀：堵左边我走右边，不可挡
    four          100_000  冲四        —— 单点杀，对手必须应，否则成五
    open_three     10_000  活三        —— 下一手可升级为活四，取胜发动机
    three           1_000  眠三        —— 单向威胁，可升级为冲四
    open_two          100  活二        —— 可升级为活三
    two                10  眠二        —— 雏形，聊胜于无

计数规则（count_patterns）：
  1. 按威胁等级从高到低处理，保证"五连不会被重复算成活四"；
  2. 同一棋型内，共享棋子的匹配合并为一个"威胁复合体"，只记一次；
  3. 已被更高优先级棋型覆盖的棋子不再参与低级计分（避免重复计分）。
计数对行反向（镜像）是对称的：模式表左右成对，规则与扫描顺序无关。

评分 = 己方棋型总分 - 对方棋型总分（evaluate），供 Minimax 叶子节点使用。
preview_score 是给走法排序用的廉价版：只看落点 4 条线上的连续棋型。
"""

from __future__ import annotations

from functools import lru_cache

from .board import BLACK, Board, EMPTY, SIZE, WHITE, opponent

# ---------------------------------------------------------------- 棋型分值表

SCORES: dict[str, int] = {
    "five": 10_000_000,   # 五连   —— 终局，直接获胜
    "open_four": 1_000_000,  # 活四  —— 双杀不可挡
    "four": 100_000,      # 冲四   —— 单点杀，对手必须防守
    "open_three": 10_000,  # 活三  —— 升级为活四的发动机
    "three": 1_000,       # 眠三   —— 单向威胁
    "open_two": 100,      # 活二   —— 升级为活三的储备
    "two": 10,            # 眠二   —— 雏形
}

# 模式表：按威胁等级降序。字符含义见模块 docstring。
PATTERN_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("five",       ("11111",)),
    ("open_four",  ("011110",)),
    ("four",       ("11110", "01111", "11011", "10111", "11101")),
    ("open_three", ("001110", "011100", "010110", "011010")),
    ("three",      ("01110", "11100", "00111", "10110", "01101",
                    "11010", "01011", "10011", "11001", "10101")),
    ("open_two",   ("001100", "000110", "011000", "010100", "001010", "010010")),
    ("two",        ("00110", "11000", "01100", "00101", "10010",
                    "10100", "00011", "01001", "10001")),
)

# 走法排序只关心大威胁（前四类），代价约为全表的 1/3
ORDER_TABLE = PATTERN_TABLE[:4]


def _map_line(cells: tuple[int, ...], player: int) -> str:
    """把一线棋格映射成模式串：己方 '1'、空 '0'、对方 '2'。

    边界等价于对方棋子，因此模式串无需补边——所有模式都不含 '2'，
    自然表达"靠墙即被封死"。
    """
    out = []
    for c in cells:
        if c == EMPTY:
            out.append("0")
        elif c == player:
            out.append("1")
        else:
            out.append("2")
    return "".join(out)


def count_patterns(s: str,
                   table: tuple[tuple[str, tuple[str, ...]], ...] = PATTERN_TABLE
                   ) -> dict[str, int]:
    """统计一行模式串中各棋型的数量（见模块 docstring 的计数规则）。"""
    counts = {name: 0 for name, _ in table}
    covered: set[int] = set()          # 已被高级棋型吃掉的棋子下标
    for name, patterns in table:
        matches: list[set[int]] = []
        for pat in patterns:
            i = s.find(pat)
            while i != -1:
                # 只记录棋子下标：共享空点不算同一个威胁
                matches.append({i + k for k, ch in enumerate(pat) if ch == "1"})
                i = s.find(pat, i + 1)
        if not matches:
            continue
        # 同棋型内：共享棋子的匹配并成一个复合体（顺序无关 -> 镜像对称）
        comps: list[set[int]] = []
        for stones in matches:
            hit = [c for c in comps if c & stones]
            if hit:
                merged = set(stones)
                for c in hit:
                    merged |= c
                    comps.remove(c)
                comps.append(merged)
            else:
                comps.append(set(stones))
        for comp in comps:
            if comp & covered:         # 已被更强棋型计过分的棋子不再重复计分
                continue
            counts[name] += 1
            covered |= comp
    return counts


@lru_cache(maxsize=16384)
def _line_value_cached(cells: tuple[int, ...], player: int, full: bool) -> float:
    table = PATTERN_TABLE if full else ORDER_TABLE
    scores = SCORES
    return sum(counts * scores[name]
               for name, counts in count_patterns(_map_line(cells, player), table).items())


def line_value(cells: tuple[int, ...], player: int, full: bool = True) -> float:
    """一条线上 player 的棋型总分（带缓存）。full=False 只算大威胁（排序用）。"""
    if cells.count(player) < 2:        # 不足两子不可能成任何棋型，快速剪掉
        return 0.0
    return _line_value_cached(tuple(cells), player, full)


# ---------------------------------------------------------------- 棋盘线表

def _build_lines(size: int = SIZE) -> tuple[list[list[tuple[int, int]]],
                                            list[list[int]]]:
    """预生成全部有效线（行/列/两对角线，长度 >= 5）与每格所属线的下标。"""
    lines: list[list[tuple[int, int]]] = []
    for y in range(size):
        lines.append([(x, y) for x in range(size)])
    for x in range(size):
        lines.append([(x, y) for y in range(size)])
    for dx, dy in ((1, 1), (1, -1)):   # 两组对角线
        for y0 in range(size):
            for x0 in range(size):
                if (dx == 1 and dy == 1 and (x0 != 0 and y0 != 0)) or \
                   (dx == 1 and dy == -1 and (x0 != 0 and y0 != size - 1)):
                    continue
                line = []
                x, y = x0, y0
                while 0 <= x < size and 0 <= y < size:
                    line.append((x, y))
                    x += dx
                    y += dy
                if len(line) >= 5:     # 更短的线装不下任何棋型
                    lines.append(line)
    cell_lines: list[list[int]] = [[[] for _ in range(size)] for _ in range(size)]
    for li, line in enumerate(lines):
        for x, y in line:
            cell_lines[y][x].append(li)
    return lines, cell_lines


LINES, CELL_LINES = _build_lines(SIZE)


def evaluate(board: Board, player: int) -> float:
    """全盘评估：player 视角 = 己方棋型总分 - 对方棋型总分。"""
    totals = {BLACK: 0.0, WHITE: 0.0}
    for line in LINES:
        cells = tuple(board.get(x, y) for x, y in line)
        if not any(cells):
            continue
        totals[BLACK] += line_value(cells, BLACK)
        totals[WHITE] += line_value(cells, WHITE)
    return totals[player] - totals[opponent(player)]


class Evaluator:
    """增量式评估器：落子/提子只重算经过该点的 4 条线，叶子评估 O(1)。

    search 在 board.play / board.undo 之后调用 refresh，保证状态同步。
    """

    def __init__(self, board: Board) -> None:
        self.board = board
        self.vals: list[list[float]] = []
        self.total: list[float] = [0.0, 0.0]      # 下标 0 = 黑，1 = 白
        for line in LINES:
            cells = tuple(board.get(x, y) for x, y in line)
            v = [line_value(cells, BLACK), line_value(cells, WHITE)]
            self.vals.append(v)
            self.total[0] += v[0]
            self.total[1] += v[1]

    def refresh(self, x: int, y: int) -> None:
        """(x, y) 状态变化后，重算经过它的 4 条线并更新总分。"""
        for li in CELL_LINES[y][x]:
            cells = tuple(self.board.get(px, py) for px, py in LINES[li])
            new = [line_value(cells, BLACK), line_value(cells, WHITE)]
            old = self.vals[li]
            self.total[0] += new[0] - old[0]
            self.total[1] += new[1] - old[1]
            self.vals[li] = new

    def evaluate(self, player: int) -> float:
        return self.total[player - 1] - self.total[2 - player]


# ---------------------------------------------------------------- 走法排序

# 连续棋型（沿一线数出来的）简化分值，仅用于排序
_RUN_SCORES: dict[tuple[int, int], int] = {
    (5, 0): 10_000_000, (5, 1): 10_000_000, (5, 2): 10_000_000,
    (4, 2): 1_000_000,   # 活四
    (4, 1): 100_000,     # 冲四
    (4, 0): 1_000,       # 死四：无赢点，威胁有限
    (3, 2): 10_000,      # 活三
    (3, 1): 1_000,       # 眠三
    (3, 0): 100,
    (2, 2): 100,         # 活二
    (2, 1): 10,
    (2, 0): 1,
    (1, 2): 1,
}


def _run_shape(board: Board, x: int, y: int, player: int) -> int:
    """若 player 占住 (x, y)，四方向连续棋型的威胁分之和（排序启发式）。"""
    total = 0
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        n = 1
        open_ends = 0
        nx, ny = x + dx, y + dy
        while board.in_bounds(nx, ny) and board.get(nx, ny) == player:
            n += 1
            nx += dx
            ny += dy
        if board.in_bounds(nx, ny) and board.get(nx, ny) == EMPTY:
            open_ends += 1
        nx, ny = x - dx, y - dy
        while board.in_bounds(nx, ny) and board.get(nx, ny) == player:
            n += 1
            nx -= dx
            ny -= dy
        if board.in_bounds(nx, ny) and board.get(nx, ny) == EMPTY:
            open_ends += 1
        if n >= 5:
            total += _RUN_SCORES[(5, open_ends)]
        else:
            total += _RUN_SCORES.get((n, open_ends), 0)
    return total


def preview_score(board: Board, x: int, y: int, player: int) -> int:
    """落子 (x, y) 的廉价评分 = 我走的成形收益 + 抢先占掉对方同型的收益。

    只看落点自身的连续棋型（O(1)），与 evaluate 的全棋型计数解耦：
    排序求"快"，终局评估求"准"，两者各司其职。
    """
    return _run_shape(board, x, y, player) + _run_shape(board, x, y, opponent(player))
