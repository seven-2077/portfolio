# 分形工坊 · fractals —— 纯标准库分形生成器

> 一棵树的全部遗传信息只有三行规则；无限放大，细节永不重复。

零第三方依赖 · Python 3.10+ · Windows 直接可跑 · 核心库约 870 行

这个项目把两条看似无关的线拧在一起：一边是 Lindenmayer 1968 年为描述植物生长
发明的**并行重写语法**（L-system），三行规则就能「长出」一棵蕨类；另一边是
Mandelbrot 集的**逃逸时间算法**，一行方程 `z ← z² + c` 画出的边界放大多少倍
都有新细节。两者共同的底层直觉是**自相似**——局部是整体的缩影。

---

## 快速启动

```bash
cd 02-projects/fun/fractals

# ① 一键生成全部演示产物到 output/（约 20 秒，含 8 张图）
python demo.py

# ② 跑测试：86 个用例，纯标准库 unittest，毫秒级
python -m unittest discover -s tests

# ③ 终端字符画：Mandelbrot ASCII 亮度渐变（已按字符 2:1 高宽比校正视口）
python -c "import demo; demo.print_ascii_mandelbrot()"
```

---

## 两个核心卖点

### 一棵树的遗传信息只有三行规则

蕨类预置的全部内容是公理 `X` 加两条产生式：

```
X → F+[[X]-X]-F[-FX]+X
F → FF
```

展开 4 代得到 1551 个符号，海龟解释成 360 条线段，就是 `output/fern.svg` 里
那棵蕨。`[` `]` 是分支的压栈与弹栈——每个侧芽回到主干的出发点继续生长，
这正是植物分枝的拓扑。同一份「遗传信息」换一个随机种子（`bush_random`
预置），长出的就是略有差异的另一棵个体：基因型相同，表型有浮动。

### 无限放大永不完结的细节

Mandelbrot 集的定义简单到一行，边界的复杂性却不可计算：无论放大多少倍，
总能翻出新的结构。本项目里这种「无限」有两个载体：

- **SVG 矢量输出**：线段坐标是浮点数，放大任意倍不糊边；
- **平滑着色**：`μ = n + 1 − log₂(ln|zₙ|)` 把整数迭代数的跳变压成连续渐变，
  边界不再是一圈圈色带（见 `fractals/mandelbrot.py` 的连续性说明）。

---

## 分形简史

### 1904：Koch 雪花——「病态曲线」的起点

瑞典数学家 Helge von Koch 构造了一条**处处连续、处处不可微**的曲线：
把每条边三等分、向外凸出一个等边三角形，无限重复。它比直线复杂，却又
没有一个确定的方向——当时的数学家称之为「病态」，谁也没想到 60 年后它
成了描述自然的钥匙。本项目的 `koch_snowflake` 预置就是它的 L-system 写法。

### 1918：Julia 与 Fatou 的竞赛

第一次世界大战的战壕里，Gaston Julia 和 Pierre Fatou 在没有计算机的年代
研究 `z ← z² + c` 的迭代行为，各自发现了这些集合的拓扑分类。战后 Julia
声名鹊起（Fatou 更低调）。然而手算的极限让这些集合沉寂了半个多世纪，
直到 Mandelbrot 用计算机把它们画了出来——`demo.py` 的四张 `julia_*.bmp`
就是 Julia 当年只能在脑中想象的「全家福」：同一个 c，不同的初始值。

### 1961–1967：海岸线悖论与分数维

物理学家 Lewis Fry Richardson 发现一个恼人的事实：测量英国海岸线，用的
尺子越短，量出来的长度越长——长度并不收敛，它依赖于测量尺度。Mandelbrot
1967 年在《Science》发表《How Long Is the Coast of Britain?》，指出该把
注意力从「长度」转向 log–log 图上的**斜率**：这个斜率对应的维数（约 1.25）
才是海岸线不粗糙程度的不变量。直线是 1 维、平面是 2 维，而海岸线卡在
两者之间——**分数维**由此诞生。

### 1968：Lindenmayer 的植物形式语法

匈牙利生物学家 Aristid Lindenmayer 研究丝状藻类的细胞分裂，他需要一种
能描述发育过程的记号：给定公理，每个时刻**所有符号同时**被替换——并行
重写。这与计算机文法（串行推导）的区别正是关键：同一时刻，主干和所有
侧芽一起生长，这恰好是植物的样子。L-system 从此成为植物建模的标准语言，
1990 年 Lindenmayer 与 Prusinkiewicz 的《The Algorithmic Beauty of Plants》
至今仍是经典。本项目的 `lsystem.py` 就是这套语法的一个小而完整的实现。

### 1975–1982：Mandelbrot 与分形几何

Benoit Mandelbrot 在 IBM 研究噪声、语言和经济数据时反复撞上同一堵墙：
经典几何（直线、圆、球）对自然界的粗糙对象无能为力。1975 年他铸造了
**fractal**（分数的）一词；1980 年他在 IBM 的机器上首次批量绘制了那个
著名的集合图像；1982 年《The Fractal Geometry of Nature》出版，分形
从此进入大众视野。Mandelbrot 集的边界至今仍有未解之谜——它是否局部
连通（MLC 猜想）是悬赏问题，而边界的 Hausdorff 维数已被证明为 2
（Shishikura）：它是「二维的曲线」。

---

## 自相似与分数维

自相似的定量版本只用到一行初中数学：如果一个图形由 **N** 个缩小为
**1/r** 的自身副本拼成，那么维数

```
D = log N / log(1/r)
```

**Koch 曲线**：每一代把一段换成 4 段、每段缩为 1/3，于是
D = log 4 / log 3 ≈ **1.2619**。测试 `test_plants.py` 里断言了它的几何
后果——第 n 代总长恰为 (4/3)ⁿ，随 n 发散（周长趋于无穷），但图形始终
落在有限面积内。**周长发散、面积收敛**，这正是分数维曲线的典型性格。

**海岸线**：Richardson 的数据在 log–log 图上是一条直线，斜率给出
D ≈ 1.25。尺子每缩短 10 倍，长度增加约 10⁰·²⁵ ≈ 1.78 倍——不是 10 倍
（那是 1 维直线的行为），也不是 100 倍（那是铺满平面的 2 维行为）。
分数维衡量的正是「图形占据空间的效率」或「粗糙度」：D 越接近 2，
边界越卷曲、越接近把平面填满。

直观对照：本项目里，Koch 雪花 D ≈ 1.26，比它更卷的龙曲线 D = 2
（龙曲线可以铺满平面区域），而树的分支结构 D ≈ 1.5 上下——
分形维数给了自然形态一把统一的尺子。

---

## 代码结构

```
fractals/
├── lsystem.py     # L-system 重写引擎：公理 + 规则 → 迭代 n 次（约 110 行）
├── turtle.py      # 海龟解释器：F/±/[] → 线段集合 + 坐标归一化（约 160 行）
├── plants.py      # 6 个预置「遗传信息」：蕨/树/Koch×2/龙/随机灌木（约 110 行）
├── mandelbrot.py  # 逃逸时间 + 平滑着色：Mandelbrot / Julia 场（约 175 行）
├── render.py      # 亮度字符表 + 调色板 + 手写 24bpp BMP writer（约 190 行）
├── svg_turtle.py  # 线段集合 → SVG（约 80 行）
└── __init__.py    # 公共 API 出口
demo.py            # 一键出图到 output/
tests/             # 86 个 unittest 用例
```

全部只用标准库（`math`、`struct`、`xml`、`random`、`dataclasses`），
BMP 文件格式是按规范逐字节拼出来的——看懂 `write_bmp` 就看懂了所有
无压缩位图。

---

## 演示产物（`output/`）

| 文件 | 内容 | 分辨率 |
|---|---|---|
| `fern.svg` | 蕨类，L-system 4 代展开 | 760×900 |
| `koch_snowflake.svg` | Koch 雪花，4 代 | 860×860 |
| `mandelbrot.bmp` | Mandelbrot 集，max_iter=300 | 800×600 |
| `julia_1_dendrite.bmp` | Julia，c = −0.7 + 0.27015i（枝晶尘） | 480×480 |
| `julia_2_rabbit.bmp` | Julia，c = −0.123 + 0.745i（兔子） | 480×480 |
| `julia_3_spiral.bmp` | Julia，c = 0.285 + 0.01i（螺旋） | 480×480 |
| `julia_4_galaxy.bmp` | Julia，c = −0.1592 − 1.0317i（旋涡星系） | 480×480 |
| `julia_atlas.bmp` | 以上四张的 2×2 图集 | 960×960 |

运行 `python demo.py` 同时会在终端打印一幅 ASCII 字符画版 Mandelbrot。
`output/` 已加入 `.gitignore`，任何时刻都可一键重建。

![蕨类](output/fern.svg)

---

## 测试

`python -m unittest discover -s tests` —— 86 个用例，毫秒级，覆盖：

- L-system 逐字精确断言（Fibonacci 词、蕨类第 1 代、并行重写）
- Koch 长度按 (4/3)ⁿ 增长、龙曲线段数 2ⁿ 翻倍、雪花归一化形状收敛
- 心瓣包含点：c = 0 不逃逸、c = 2+i 逃逸、平滑值夹逼整数计数
- 平滑着色连续性：平方恒等式 μ(n, M) = μ(n+1, M²)、逃逸边界台阶 < 0.3
- 海龟分支栈平衡（下溢 / 未闭合均抛 `TurtleError`）、归一化退化边界
- BMP 读回验证（文件头 / 信息头 / BGR 像素 / 4 字节对齐 / 行序）
- SVG 可被 `xml.etree` 解析、线段数与 `<line>` 元素一一对应

---

## English Summary

A pure-standard-library fractal generator (Python 3.10+, zero dependencies,
runs on Windows out of the box) that combines two classical constructions:
an **L-system string-rewriting engine** with a turtle interpreter (branch
stack `[]`, normalization, SVG output) for plants and curves — fern, tree,
Koch snowflake, dragon curve — and **escape-time rendering** of the
Mandelbrot/Julia sets with smooth coloring (`μ = n + 1 − log₂(ln|z|)`),
an ASCII terminal view, and a hand-written 24-bit BMP writer built from
`struct` alone.

`python demo.py` regenerates all eight figures into `output/` in about
twenty seconds; `python -m unittest discover -s tests` runs the 86-test
suite. The project is a hands-on tour of self-similarity and fractional
dimension — the coastline paradox (Richardson, Mandelbrot 1967), Koch's
1904 curve (D = log4/log3 ≈ 1.262), Lindenmayer's 1968 parallel rewriting
grammar for plant morphology, and Mandelbrot's 1982 synthesis.

---

## Roadmap

- **IFS 迭代函数系统**：Barnsley 蕨——用 4 个仿射变换 + 概率喷洒，
  以 100 倍于 L-system 的压缩比得到同一只蕨；顺带打通 L-system 与 IFS
  这两种自相似描述的对偶视角。
- **三维 Menger 海绵 / Sierpinski 四面体**：把逃逸时间推到三维网格，
  输出切片 PPM 序列或 OBJ 网格；海龟解释器加 `& ^ \\ /` 俯仰与偏航指令
  即可画空间曲线。
- **参数化 L-system**：带参数的产生式（如 `A(s): s>0 → A(s·0.7)`），
  为枝条粗细、曲率连续变化铺路。
- **深缩放**：双精度在放大 ~10¹³ 倍后像素化，引入 perturbation 理论
  （中心流形 + delta 迭代）突破极限。
- **交互式查看器**：SDL/pygame 或 WebGL 前端，鼠标拖拽平移、滚轮缩放
  实时重算。
