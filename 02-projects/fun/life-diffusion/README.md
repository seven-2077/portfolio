# 生命与扩散 · 涌现实验室 · Life Diffusion

> 只写局部规则，全局结构凭空涌现。
> 康威生命游戏（离散 × 计算） × Gray-Scott 反应扩散（连续 × 形态发生），
> 一个零依赖纯 Python 的跨学科乐趣实验室。

---

## 快速启动

环境要求：**Python 3.10+，零第三方依赖**，Windows / macOS / Linux 均可直接运行。

```powershell
cd 02-projects/fun/life-diffusion

# 跑完整 demo（终端动画 + 5 个 SVG 产物到 output/）
python demo.py

# 跑全部测试（65 条，约 10 秒）
python -m unittest discover -s tests
```

三行代码感受一下「涌现」：

```python
from lifelab import GameOfLife, get_pattern

life = GameOfLife(40, 16)                       # 稀疏坐标集表示活细胞
life.add(get_pattern("glider").cells_at((2, 2)))  # 放入一只滑翔机
life.run(20)                                    # 演化 20 代：它斜着走了 5 格，population 恒为 5
```

```python
from lifelab import GrayScott

sim = GrayScott.from_preset(96, 96, "stripes")  # 迷宫条纹参数
sim.run(600)                                     # 600 步显式有限差分
print(sim.stats())                               # {'mean_v': ..., 'edge_density': ..., 'occupied': ...}
```

---

## 「涌现」是什么

复杂系统里最迷人的一个词。它的意思是：**全局层面凭空出现的秩序，没有任何一个中央蓝图在指挥，只靠每个个体遵守极简单的局部规则。**

生命游戏是教科书级的例子。Conway 1970 年只定了三条规则（下文 B3/S23），结果网格上长出了会走路的「滑翔机」、会开火的「枪炮」、会互相吞并的「吃豆人」——没有任何一条规则写着「滑翔机」这三个字。滑翔机是**被涌现出来的**。

反应扩散是另一个例子，只不过主角从离散格子换成了连续浓度场。Turing 1952 年猜想：两种相互作用的化学物质（一个激活、一个抑制）在组织里边反应边扩散，就能自发长出斑点、条纹、迷宫——**动物的花纹可能就是这样长出来的**，不需要一个「画花纹的基因蓝图」，只需要反应和扩散这两条规则。

两个模型，一个共同的哲学：**简单规则 → 复杂结构**。这正是本项目把它们放在一起的原因。

---

## 康威生命游戏：三条规则与图灵完备

### 规则（B3/S23）

网格上每个细胞有 8 个 Moore 邻域邻居，每一代同步更新：

- **B3（Birth）**：死细胞恰好遇到 3 个活邻居 → 出生
- **S23（Survival）**：活细胞遇到 2 或 3 个活邻居 → 存活
- **其余** → 死亡（邻居 <2 属孤单死，>3 属拥挤死）

就这三条。本实现用**活细胞坐标集合**做状态（稀疏、省内存，滑翔机这类图案只占几十个坐标），边界支持有限平面（默认）与**环面**（`wrap=True`，上下左右首尾相接）两种模式；`from_text()` 可直接加载经典 Gosper 风格字符画。

### 图案库（`lifelab/patterns.py`）

- **glider 滑翔机**：4 步恰好平移 (1,1)，宇宙中最著名的「行走的结构」
- **blinker 闪烁灯**：周期 2 的最简振荡器
- **pulsar 脉冲星**：周期 3，48 个细胞的大型振荡器（相位人数 48 → 56 → 72）
- **gosper_glider_gun**：Bill Gosper 团队 1970 年造出的第一门「滑翔机枪」，每 30 代吐出一只滑翔机，**无限增长**——它一举推翻了「任何有限图案最终要么死绝、要么变成周期」的猜想

每个图案都带完整元信息（发现者、年份、周期、是否平移、平移向量），可按别名检索。

### 图灵机等价性

Conway 及后来的研究者证明了生命游戏是**图灵完备**的：用滑翔机当信号、用碰撞当逻辑门，可以在网格上构造出通用图灵机——**给它足够大的画布和初始图案，它可以计算任何可计算函数**。一个只有三条规则的玩具，和你正在用的这台计算机，在计算能力上是同一类东西。这正是「涌现」最硬核的注脚。

---

## Gray-Scott 反应扩散：Turing 1952 的花纹之谜

### Turing 与《形态发生学的化学基础》

1952 年，Alan Turing 发表了《The Chemical Basis of Morphogenesis》。他问了一个当时没人能回答的问题：**一只没有任何花纹的胚胎，怎么会长出规则的斑点和条纹？** 他的答案是「反应-扩散」——两种 morphogen（形态发生素）一边互相反应、一边向四周扩散，微小的初始扰动会被不稳定性放大，最终自组织成稳定的空间图案。Turing 用这 30 页论文开创了理论生物学的一个分支。

### Gray-Scott 模型

Gray-Scott 是 Turing 思想最经典的可数值实现之一，两种浓度场 U、V 的动力学为：

```
∂U/∂t = Du·∇²U − U·V² + F·(1 − U)        # U 被 V 消耗，同时以速率 F 从「池」补给
∂V/∂t = Dv·∇²V + U·V² − (F + k)·V        # V 由 U·V² 反应生成，以速率 F+k 被清除
```

- **Du、Dv**：两种物质的扩散系数（默认 0.16 / 0.08，V 扩散更慢）
- **F（feed 补给率）**、**k（kill 消除率）**：两个旋钮，只调它们就能切换出完全不同的生命形态——Pearson 1993 年系统研究了这方参数空间，分出了斑点、条纹、蠕虫等若干「相区」

本实现用**显式 FTCS 有限差分**（前向时间中心空间），拉普拉斯支持 **5 点十字模板**与 **9 点 Mehrstellen 加权模板**（`lap='5' / '9'`），每步对 U、V 做 **[0, 1] 浓度裁剪**保证数值稳定，边界默认环面。热点循环用预计算的平铺邻居索引表，纯 Python 也能跑到 96×96 × 600 步秒级。

### 三组预设（demo 内置）

- **spots 斑点型**（F=0.0367, k=0.0649）：孤立圆点不断分裂，mitosis 区
- **stripes 条纹型**（F=0.0300, k=0.0620）：细长条纹蜿蜒交织，迷宫区
- **worms 蠕虫型**（F=0.0260, k=0.0550）：低补给低消耗，蠕虫状结构密集蔓延

同一套规则、同一颗种子，只换两个数字，长出来的「动物」就完全不同——这和猎豹长斑、斑马长纹、长颈鹿长网纹可能是同一个道理（学界至今仍视反应扩散为动物花纹的主流候选假说之一）。

---

## 项目结构

```
life-diffusion/
├── lifelab/
│   ├── __init__.py          # 包入口：GameOfLife / GrayScott / PRESETS / PATTERNS
│   ├── game_of_life.py      # B3/S23 引擎：字符画加载、步进/批量演化、环面边界
│   ├── patterns.py          # 图案库 + 元信息（glider/blinker/pulsar/gun）
│   ├── grey_scott.py        # Gray-Scott：FTCS、5/9 点拉普拉斯、浓度裁剪、预设
│   └── viz.py               # 终端 ANSI 动画 + SVG（胶片/热力马赛克/图集）
├── tests/                   # 65 条单元测试（4 个测试文件）
├── demo.py                  # 一键 demo
├── output/                  # demo 产物（SVG + 预览 PNG）
├── README.md / LICENSE / .gitignore
```

核心代码 4 模块约 **773 行**（含 demo 总计约 892 行），全部零依赖。

---

## Demo 输出

`python demo.py` 一次跑完两部分（实测约 27 秒）：

**a) 滑翔机**——终端 ANSI 清屏动画 20 步（共渲染 21 帧，4 代平移一格），
并导出关键时刻胶片 `output/life_glider_strip.svg`（gen 0,4,8,…,20 共 6 帧）。

**b) 反应扩散**——三组 feed/kill 各跑 600 步（96×96 网格），全部落在 `output/`：

| 产物 | 内容 |
|------|------|
| `output/rd_spots.svg` | 斑点型终态（gen 600） |
| `output/rd_stripes.svg` | 条纹型终态（gen 600） |
| `output/rd_worms.svg` | 蠕虫型终态（gen 600） |
| `output/rd_atlas.svg` | 三联图集：3 预设 × 3 时刻（gen 200/400/600）灰度马赛克 |
| `output/life_glider_strip.svg` | 滑翔机关键时刻胶片 |

SVG 全部按行游程压缩（同一颜色的连续像素合并成一个 `<rect>`）：单张 96×96 浓度场压缩到 4–9 千条矩形、250–510 KB，三联图集（9 面板）约 3 MB，浏览器直接打开即可查看。`output/*.png` 是配套的快速预览图。

---

## 测试

```powershell
python -m unittest discover -s tests
```

**65 条测试全绿**，覆盖任务要求的全部要点：

- `test_game_of_life`（20 条）：B3/S23 规则边界（孤独死 / 恰 3 出生 / 拥挤死 / 2-3 存活）、glider 4 步与 8 步平移、字符画往返、越界报错、环面折返、快照独立性
- `test_patterns`（17 条）：图案元信息、四种图案几何、blinker 周期 2、pulsar 周期 3、枪炮 240 步持续发射滑翔机
- `test_grey_scott`（13 条）：单步/多步确定性、200 步浓度不越出 [0,1]、极端参数裁剪、5 点与 9 点模板差异、**三组预设的边缘密度与占据率统计可区分**
- `test_viz`（15 条）：终端帧数与 ANSI、SVG 结构可 `xml.etree` 解析、题注转义、图集尺寸与校验

---

## English Summary

**Life Diffusion** is a zero-dependency, pure-Python laboratory of emergence that pairs two classic complex-system models:

1. **Conway's Game of Life (B3/S23)** — a sparse-coordinate cell engine with Gosper-style pattern loading, step/batch evolution, bounded or toroidal edges, and a preset library (glider, blinker, pulsar, Gosper glider gun) with full metadata. The game is Turing-complete: three local rules suffice to simulate a universal Turing machine.
2. **Gray-Scott reaction-diffusion** — an explicit FTCS scheme with 5-point or 9-point Mehrstellen Laplacians, configurable feed/kill/diffusion coefficients, and [0,1] concentration clipping for stability. Following Turing's 1952 *Chemical Basis of Morphogenesis*, three feed/kill presets (spots / stripes / worms) produce statistically distinct patterns from identical seeds.

Output: ANSI terminal animation plus run-length-compressed SVG snapshots, heat mosaics, and a pattern atlas. 65 unit tests, all green. See `demo.py` and `output/`.

---

## Roadmap

- **Lenia**（连续生命）：Bertrand Chan 2018 年把 Life 推广到连续时间/空间/状态，生命游戏从「三条规则的像素玩具」升级为可进化的连续生命形态学；本项目的游戏引擎可平滑移植到 Lenia 的核函数框架
- **规则空间随机搜索**：对 B/S 规则空间（2^18 量级的规则号）做随机采样与统计筛选，自动发掘「有趣」的规则——类似 Life census 与 Generative Rules 的玩法，可以写成自动化脚本，也是复杂系统研究的正统方法论
- 性能与呈现：热点循环可换 `array`/`numpy` 可选加速（保持零依赖核心）、Web 交互画布、更多 Pearson 相区与 Schnakenberg 等其他 RD 模型

---

## License

[MIT](LICENSE) © 2026 Seven
