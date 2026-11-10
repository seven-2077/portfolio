# 太阳系星历计算器（Solar System Ephemeris）

用**开普勒方程**从 J2000 轨道根数算出八行星的真实位置——日心黄经、地心黄经、
所在星座，再画成一张黄道十二宫星图。纯 Python 标准库，零依赖。

核心卖点：**算出来的行星黄经和观星 App 对得上**。实测 1999-05-20 与独立星历
对照，八行星地心黄经误差全部 ≤ 1.1°；2026 年金木合只差 0.3 小时。

这个项目也是个科学史标本：开普勒 1609 年就是被这几个数字折磨了八年，
才写下"火星是椭圆"那句话。

---

## 快速启动

```bash
cd 02-projects/fun/solar-system

python demo.py                 # 今天的八行星黄经表 + 黄道星图
python demo.py 1999-05-20      # 算任意日期（取当日 12:00 UTC）
python demo.py 1999-05-20 13:45  # 精确到分钟

python -m unittest discover -s tests   # 50 个测试
```

demo 会依次输出：

1. 八行星 + 太阳的黄经表（日心 / 地心 / 地心距离 / 所在星座）
2. 黄道星图 SVG → `output/zodiac_YYYY-MM-DD.svg`
3. 已知天象对照：2026-06-09 金木合、2020-12-21 土木大合的计算偏差

## 项目结构

```
solar-system/
├── orbit/
│   ├── kepler.py       # 开普勒方程牛顿迭代（1e-12 收敛 + 二分兜底）
│   ├── elements.py     # J2000 八行星轨道根数表 + 一阶长期项（JPL 来源）
│   ├── planet.py       # 根数 → 日心黄道坐标 → 黄经黄纬 → 地心位置
│   ├── time_utils.py   # 儒略日、1900/2000 历元换算、时区约定
│   └── chart.py        # SVG 黄道带星图
├── tests/              # 50 个单元测试
├── demo.py             # 入口
├── output/             # 生成的星图（demo 自动创建）
├── README.md  LICENSE  .gitignore
```

## 计算流水线

```
J2000 根数(a,e,i,ω,Ω,M₀) ──长期项外推──► 当日根数
        │
        ▼  M = M₀ + Ṁ·T
   开普勒方程  M = E − e·sin E   ← 牛顿迭代（本项目核心）
        │
        ▼  E
   轨道面坐标 x' = a(cosE − e), y' = a√(1−e²)sinE
        │
        ▼  三次旋转 R_z(−Ω)·R_x(−i)·R_z(−ω)（JPL 矩阵）
   日心黄道直角坐标 (x, y, z)
        │
        ├──► 日心黄经 λ = atan2(y, x)
        │
        ▼  地心矢量 = 行星 − 地球
   地心黄经 / 黄纬（观星 App 展示的就是这个）
        │
        └──► 太阳地心黄经 = 地球日心黄经 + 180°
```

## 开普勒方程的来历：1609 年，火星与第谷的八年拉锯

第谷·布拉赫用二十年把行星位置测到了 1–2 角分的精度——这在望远镜发明之前
是人类观测的极限。1601 年第谷去世，弟子开普勒继承了这份火星数据。

开普勒当时的信念是哥白尼体系 + **正圆轨道**：行星绕太阳做匀速圆周运动，
最多加一个偏心轮修正。他试了一个又一个模型，算出来的火星位置和第谷数据
总差着 **约 8 角分**——而第谷的观测误差只有 1–2 角分。这 8 角分就是
四百年天体力学的起点：不是数据错了，是"圆"错了。

1605 年他先放弃圆，改用**卵形线**；1609 年 9 月《新天文学》（Astronomia Nova）
出版，宣布火星轨道是**椭圆**，太阳位于椭圆一个焦点上。同年他写下面积定律
（等时间扫过等面积）。十年后（1619）《世界的和谐》给出第三定律 T² ∝ a³。

而把椭圆运动换算成"某时刻行星在哪"，靠的就是这篇里的方程：

$$M = E - e\sin E$$

M 是**平近点角**——一个假设以恒定角速度均匀流逝的"假想时间角"；E 是
**偏近点角**——椭圆上的几何位置角。两者隔着一个 `e·sin E` 的修正项，
而这个修正项里 E 本身就在要解的方程里：**超越方程，无解析解**。
开普勒当年用手算迭代逼近它；今天换成牛顿迭代，四百年一步跨完。

> 顺带一提：`ω`（近日点幅角）+ `Ω`（升交点经度）= `ϖ`（近日点黄经）只是
> 一个**角度和**。轨道有倾角 i 时，近日点真正投影到黄道上的黄经是
> `Ω + atan2(sin ω · cos i, cos ω)`，两者相差约 `i·sin ω`——水星约 0.18°。
> 本项目的旋转矩阵（照抄 JPL 公式）天然给出了正确的投影值，
> `tests/test_planet.py` 里专门验证了这一点。

## 牛顿迭代为什么有效

对 f(E) = E − e·sin E − M，求导得 f′(E) = 1 − e·cos E。三个性质保证了它好用：

1. **单调有根**：椭圆轨道 e < 1，故 f′ ≥ 1 − e > 0 恒正，f 严格单调，
   核唯一，不存在迭代到错误根的问题。
2. **局部二次收敛**：f″ = e·sin E 有界，牛顿法在根附近每迭代一次有效
   数字翻倍。取经典初值 E₀ = M + e·sin M 后，本项目根数（e ≤ 0.206）
   通常 **4–5 次**就压到 1e-12（约 6×10⁻⁶ 角秒量级的残差）。
3. **发散保护**：万一迭代失控（比如初值极差），根必落在 `[M−e, M+e]`
   内（因 |e·sin E| ≤ e），这个括号上 f 变号，直接转**二分法**兜底，
   单调函数上二分必然收敛。`max_iter` 参数就是牛顿阶段的保险丝。

牛顿本人 1669 年在《流数术》里给出这个方法（后由 Raphson 1690 年改进
成今天的形式），而开普勒比他早六十年用手完成了同样的事。

## 精度诚实声明

**这是教学/科普级简化历表，不是专业星历。** 具体误差来源：

| 误差源 | 量级 |
| --- | --- |
| 根数只取 J2000 + 一阶长期项（丢掉二次项与周期摄动） | 主要来源 |
| 忽略章动、光行差（−20.5″）、ΔT（UT≈TT，2026 年约 72 s） | < 0.01° |
| 地月系质心当地球用 | < 0.003° |
| **综合（黄经）** | **约 ±1°** |

JPL 官方对这套近似的标注是 1800–2050 年内日心黄经误差 10″–600″；
但叠加各种简化后，**对外承诺按 ±1° 保守估计**——对"今晚木星在哪个星座、
几度"这类问题完全够用，对掩星预报、航天测轨则远远不够。

专业级要上 **VSOP87**（行星级数解，角分级）或 **JPL DE440**（数值积分，
角秒级）。Roadmap 里有计划。

**实测对照**（demo 自带）：

- 2026-06-09 19:48 金木合：计算 20:08，偏差 **+0.3 小时**
- 2020-12-21 18:20 土木大合：计算 12-22 04:35，偏差 **+10.3 小时**
- 1999-05-20 与独立星历逐星对照：太阳 0.5°、金星 0.6°、火星 0.1°、
  木星 0.2°、土星 0.05°、天王星/海王星 ≈0.00°、水星 1.1°

## 测试

```bash
python -m unittest discover -s tests
# Ran 50 tests — OK
```

覆盖：开普勒残差 < 1e-10（网格 × 6 个偏心率）、e=0 退化 E=M、
与独立二分法对照、发散兜底、儒略日已知值（2451545.0 / 2446822.5）、
1900/2000 历元换算、时区感知转换、2000-01-01 太阳黄经 ≈280°±2°、
黄经 ∈ [0,360) 网格、近日点/远日点几何（r = a(1∓e) 与投影黄经）、
**金木合/土木合 ±3 天**、SVG 可解析与结构完整。

## English Summary

A zero-dependency Python ephemeris calculator. It solves Kepler's equation
`M = E − e·sin E` by Newton iteration (tolerance 1e-12, with a guaranteed
bisection fallback), converts J2000 Keplerian elements (JPL SSD approximate
elements, with secular rates) into heliocentric and geocentric ecliptic
longitudes for all eight planets, converts dates to Julian Days (with an
explicit UTC convention and 1900/2000 epoch helpers), and renders a zodiac
belt chart as SVG. The demo prints today's planet longitudes, draws the chart,
accepts any date on the command line, and validates itself against two known
conjunctions (2026 Venus–Jupiter: +0.3 h; 2020 Jupiter–Saturn: +10.3 h).
Honest accuracy statement: simplified J2000 model, ≈ ±1° in longitude —
fine for stargazing, not for navigation. 50 unit tests included.

## Roadmap

1. **VSOP87 精化** —— 移植 VSOP87D 行星级数的头部项（几百个三角级数），
   把黄经误差从 ±1° 压到角分级；仍是纯标准库可承载的计算量。
2. **月球** —— 简化 ELP/Meeus 月球级数（约 60 项），支持月相、合月、
   月掩星预报；顺带把 ΔT 修正做进 `time_utils`。
3. **行星合预报器** —— 把 `find_conjunction` 从"给窗口找合"升级为
   任意行星对的全年合/冲/刑列表 + 逆行识别，输出日历文件。
4. 视星等与升落时刻（需要黄赤交角、纬度、大气折射）
5. 交互式星图（SVG 加拖拽/缩放，或导出 JSON 星历表给前端）

## License

MIT，见 [LICENSE](LICENSE)。轨道根数数据来自 JPL SSD 公开近似历表
（Standish & Williams 1992），公有领域数据，注明出处即可。
