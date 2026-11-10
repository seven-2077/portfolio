# 五子棋 AI · gomoku-ai · 终端五子棋 AI

亲手造一个下得过你的对手。

这是一个零依赖的纯 Python 五子棋引擎：15×15 棋盘、Minimax 搜索、Alpha-Beta 剪枝、
棋型启发式评分，全部从零实现。当它走出一手"预判了你三步"的棋时，你知道那不是
黑箱——那是你自己的搜索树在替你算。

跨学科乐趣项目：博弈论（对抗式搜索）× 搜索算法（剪枝与状态空间）。

## 快速启动

要求 Python 3.10+，纯标准库，无需安装任何依赖。在项目根目录执行：

```bash
cd 02-projects/fun/gomoku-ai

# 人机对战（你执黑先行）
python -m gomoku.cli

# AI vs AI 自对弈，棋谱写入 output/
python -m gomoku.selfplay

# 三段演示：取胜手 / 自对弈棋谱 / 剪枝节点对比
python demo.py

# 测试（45 个用例）
python -m unittest discover -s tests
```

落子输入支持两种等价写法：`H8`（列字母 + 行数字）与 `8,8`（列号 + 行号），
列是 A-O、行是 1-15，与棋盘上打印的坐标一一对应；`q` 退出。

难度三档：浅 = 深度 2 / 候选宽 6；中 = 深度 4 / 候选宽 10；深 = 深度 6 /
候选宽 12 / 时间预算 10 秒。AI 每手会打印用时、访问节点数与评估分。

## 项目结构

```
gomoku-ai/
├── gomoku/
│   ├── board.py       # 15×15 棋盘：落子/提子、邻域候选走法（半径参数）
│   ├── rules.py       # 五连判定（横竖斜、边界安全）、平局判定、杀点识别
│   ├── evaluate.py    # 模式评分：七级棋型分值表 + 双向计数 + 增量评估器
│   ├── search.py      # Negamax + Alpha-Beta + 迭代加深 + 胜负短路
│   ├── cli.py         # 终端对战：渲染、坐标解析、难度档、耗时打印
│   └── selfplay.py    # AI 自对弈，文本棋谱落盘 output/
├── tests/             # 45 个用例：规则/棋盘/棋型/搜索
├── demo.py            # 三段演示（取胜手、自对弈、剪枝对比）
├── output/            # 对局棋谱与 demo 报告
├── README.md  LICENSE  .gitignore
```

核心实现（`gomoku/` 七个文件）约 740 行，测试约 410 行。

## Minimax 原理：为什么双方都最优

五子棋是零和、完全信息、双人交替的博弈。Minimax 的做法是把整棵对局树展开：
轮到我走的一层取所有着法的最大值，轮到对手的一层取所有着法的最小值——
对手一定回敬他所能找到的最强应对，而不是配合我赢。

"双方都最优"的含义是归纳出来的：在深度为 0 的叶子上我们用启发式评估给局面打分；
倒数第二层的我方会选择叶子里对我最有利的一手，因为它假定再往后对手会把分数压到最低。
逐层向上递推，根节点得到的分数就是"在对手不犯错的前提下，我最多能拿到的分"。
所以它不赌对手失误；一盘棋里 AI 看到的"必胜分"（接近 10⁹ 的 WIN_SCORE），
意味着无论对手怎么应都挡不住——demo a 里那手活四就是这么被算出来的。

代码里写成 Negamax 形式（`search.py`）：零和博弈满足
"我方最优值 = -(对方最优值)"，于是同一套递归换个符号就能让黑白双方交替复用，
实现只有一份。配上迭代加深（1..depth 逐层搜索），低深度结果永远兜底，
也天然支持"时间预算"式难度控制。

## Alpha-Beta：为什么等价且更快

等价性来自一个干净的窗口论证。递归带着 `(alpha, beta)` 区间下行：
alpha 是"我方已保证能拿到的下限"，beta 是"对方已保证能压到的上限"。
当某棵子树的取值注定落在窗口之外——它再好也改变不了任何上层 max/min 的选择——
整棵子树就被剪掉，不再展开。被剪的枝对根节点的最小最大值没有贡献，
所以 Alpha-Beta 返回的分数与完全展开的裸 Minimax **严格相等**。
这不是近似，是定理；测试里 `test_same_score_depth3/depth4` 就是它的实验验证：
同一局面、同一候选集、同分同着。

更快是因为剪枝量依赖着法顺序：最强的着先走，alpha 抬得快，
后面兄弟子树整片作废。理想情况下复杂度从 O(b^d) 降到 O(b^(d/2))——
等效于免费翻倍搜索深度。demo c 的实测（中局 12 手、深度 4、候选宽 10）：

```
                 节点数      截断数      耗时       评估分
裸 Minimax        10710         -      1.33s        -9090
Alpha-Beta          355       125      0.16s        -9090
```

节点缩减 30.2×，耗时缩减 8.4×，分数一字不差。

## 启发式评分与剪枝的关系

先分清两件事：评分**不参与**剪枝的正确性，正确性完全由上面的窗口论证保证；
评分只影响两处速度——

其一是排序。`preview_score` 用廉价的"落点连续棋型"给候选着打分（只看落点自身
四条线的活四/冲四/活三结构，O(1)），让强着排在前面。评分越准，alpha 抬得越快，
剪得越多；排序差一点，结果仍然正确，只是节点数回升。

其二是叶子估值。搜索不可能算到终局，深度尽头用 `evaluate` 给局面打分：
把每条线映射成模式串（己方 1、空 0、对方 2，边界天然等于对方棋子），
按威胁等级从高到低计数——活五 > 活四 > 冲四 > 活三 > 眠三 > 活二 > 眠二——
共享棋子的匹配合并成一个"威胁复合体"只记一次，保证镜像对称与不重复计分。
分数 = 己方棋型总分 - 对方棋型总分，作为 Minimax 的残局估值。

两者的分工是刻意的：排序求"快"，叶子求"准"。`Evaluator` 增量维护——
落子只重算经过该点的 4 条线，叶子评估 O(1)，这是深度 6 能在两秒内跑完的前提。
当然评分也有固有上限：局势的"火候"超过搜索深度时会出现视界效应
（AI 为眼前的小亏换掉未来的杀招），这正是加深搜索与更强评估要解决的问题。

## 实测速览

- 取胜手演示：活三残局 0.14s、395 节点，找到活四双杀，评估 +999999991（必胜）
- 自对弈：中档（深度 4）一局 23 手、约 5 秒，棋谱写入 `output/selfplay_*.txt`
- 深档：中局深度 6 / 候选宽 12，约 4600 节点、2 秒内应手
- 测试：45 个用例全部通过，约 4.4 秒

## English Summary

A zero-dependency terminal Gomoku (five-in-a-row) engine in pure Python 3.10+.
The board module handles 15×15 state and radius-based candidate generation;
the rules module detects wins across all four directions with boundary safety;
the evaluate module scores seven threat levels (open five, open four, rush four,
open three, sleep three, open two, sleep two) with mirror-symmetric pattern
counting and an incremental evaluator; the search module implements Negamax with
Alpha-Beta pruning, iterative deepening, move ordering and win short-circuits.
Alpha-Beta provably returns the exact same score as bare Minimax while cutting
roughly 30× fewer nodes in the measured mid-game benchmark. The CLI provides
human-vs-AI play with three difficulty tiers, and self-play records games as
plain-text files under `output/`. Run `python demo.py` for a forced-win demo,
an AI-vs-AI game record, and a pruning node-count comparison.

## Roadmap

- MCTS：蒙特卡洛树搜索补足开放局面的评估质量，用胜率替代棋型打分，
  解决视界效应；可与现有 Minimax 混合（终局切换）。
- 开局库：把常见定式（花月、浦月等）前十几手固化为查表，开局又快又稳，
  也是喂给自对弈的高质量开局分布。
- 网络对战：WebSocket 后端 + 网页棋盘，把终端引擎搬到浏览器里和朋友下；
  配合 Elo 评级与匹配，形成最小可用的对战闭环。
- 难度自适应：按自对弈胜率动态调节深度/候选宽，而不是固定三档。

## License

MIT，见 [LICENSE](LICENSE)。
