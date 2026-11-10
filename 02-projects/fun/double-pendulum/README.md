# 双摆混沌模拟器 · Double Pendulum Chaos

两根杆、两个球、一组微分方程 —— 初值只差 **0.0001 rad**，两秒后轨迹彻底分道扬镳。
纯 Python 标准库从零实现：Lagrange 推导 → RK4 积分 → SVG 轨迹对比 / 能量漂移 / 分岔曲线 → 终端 ASCII 动画。

```
初值差 1e-4 rad  →  2.03 s 后相空间距离超过 0.1  →  10 s 后两组状态相差 ~40 倍杆长尺度
```

---

## 快速启动

要求 **Python 3.10+**，零第三方依赖（Windows / macOS / Linux 皆可）。

```bash
cd 02-projects/fun/double-pendulum

python demo.py                          # 一键演示：SVG + 分岔时刻 + 终端动画
python demo.py --no-anim                # 只要图和数字
python demo.py --delta 1e-5 --t-end 20  # 换扰动幅度与时长
python -m unittest discover -s tests    # 49 项测试
```

`demo.py` 会做三件事：

1. 两组初值（θ₁ = 170° 与 170° + 1e-4）同步仿真 10 s，打印**分岔时刻**与能量漂移；
2. 生成三张 SVG 到 `output/`；
3. 终端 ASCII 动画（交互终端下 `q` / `Esc` 退出，非交互终端自动抽样打印）。

### 产物（`output/`）

| 文件 | 内容 |
|------|------|
| `trajectory_compare.svg` | 双轨迹对比：红/青两色、透明叠加、随时间渐变加深 |
| `energy_drift.svg` | 能量漂移 ΔE(t)：数值质量体检（应贴近 0） |
| `divergence_log.svg` | 分岔距离对数曲线：指数增长段近似直线 |

---

## 项目结构

```
double-pendulum/
├── demo.py               一键演示入口
├── pendulum/
│   ├── ode.py            运动方程（Lagrange 推导注释 + 一阶标准形式）
│   ├── energy.py         动能 / 势能 / 总能量
│   ├── integrate.py      RK4 定步长积分器（变步长扩展位已留）
│   └── trace.py          轨迹采集：双初值并行 + 分岔时刻
├── viz/
│   ├── svg_out.py        SVG 三件套
│   └── ascii_anim.py     终端 ASCII 实时动画（msvcrt 非阻塞）
├── tests/                49 项单元测试
├── output/               产物（demo 生成）
├── README.md · LICENSE (MIT) · .gitignore
```

---

## 混沌原理讲解

### 双摆为什么混沌

单摆是「教科书式的善良」：非线性但可解，小角度周期 `2π√(l/g)`，相空间里的轨道是一圈圈闭合曲线。双摆把第二个摆挂在第一个的末端，事情就变了。

方程里同时存在三类「捣乱项」——

- **几何非线性**：`sinθ` 让回复力不再与位移成正比；
- **速度平方耦合**：`ω₂²·sin(θ₁-θ₂)` 这类项让快慢运动互相拉扯；
- **惯性耦合**：质量矩阵里的 `m₂l₁l₂cos(θ₁-θ₂)` 把两个角加速度锁在一起，摆 2 的动作会实时改写摆 1 的受力。

结果是：方程没有一般解析解，只能数值求解；能量守恒把轨迹关在相空间的有限区域里跑不掉；而非线性又让相邻轨迹指数分离 —— 于是在有限空间里无限缠绕、永不重复。**确定性的方程 + 长期不可预测**，这就是混沌。

### 相空间：把「摆的姿态」画成一个点

任一时刻系统的完整状态是 `(θ₁, ω₁, θ₂, ω₂)`，四个数构成一个 **4 维相空间**：

- 系统的演化 = 一个点在相空间里画出一条轨迹；
- 轨迹**永不相交**（解的唯一性定理）：若相交，同一个状态将演化出两条未来，与确定性矛盾；
- 单摆的 2 维相空间里轨道闭合 ⇒ 周期运动；双摆的 4 维相空间里，混沌区的轨道永不闭合，反复经过「看起来一样」的状态却永远接不上。

`trajectory_compare.svg` 画的是摆球 2 的端点轨迹 —— 相空间轨迹在物理空间的投影；`divergence_log.svg` 则直接量两条轨迹在相空间里的距离 `d(t)`。

### 对初值的敏感依赖（本项目的核心演示）

两组初值只差 `Δθ₁ = 1e-4 rad`（约 0.006°），其余完全相同、方程完全相同、积分器完全相同 —— 没有任何随机数。然后：

```
t = 0 s     距离 1.0e-04   （肉眼完全重合）
t ≈ 1.3 s   距离 0.01      （开始能看出差别）
t ≈ 2.0 s   距离 0.1       ← 分岔时刻，两组轨迹正式「分家」
t = 10 s    距离 ~3.8e+01  （一个在转圈，一个在甩动，毫无关系）
```

距离按 `d(t) ≈ d₀·e^{λt}` 指数增长，本演示的 λ ≈ 2/s。**放大倍数 ≈ 4×10⁵** —— 混沌把「微不足道」放大成「面目全非」。

### Lorenz 1963 与蝴蝶效应的来历

这段历史值得完整讲一遍，因为它是「确定性系统能否长期预测」这个问题的分水岭：

- **1961 年**，气象学家 Edward Lorenz 在 MIT 用一台 Royal McBee LGP-30 小型计算机求解简化的大气对流模型。为了省事重跑一段长计算，他从打印结果的中段重启，把 `0.506` 手抄成 `0.506127`（多保留了三位小数）。微小到荒谬的输入差异，让两条轨迹在几分钟内彻底分道扬镳。
- **1963 年**，他发表 *Deterministic Nonperiodic Flow*（《大气科学杂志》），指出这类系统非周期、对初值敏感，长期预报存在原理性上限。
- **1972 年**，他准备赴华盛顿在美国科学促进会演讲，题目被同事 William Markson 定为：*Does the flap of a butterfly's wings in Brazil set off a tornado in Texas?*（巴西一只蝴蝶扇动翅膀，能否在得克萨斯引起龙卷风？）——「蝴蝶效应」从此进入大众语言。

往前追溯一步：**Poincaré** 在 1890 年代研究三体问题时就已发现确定性系统可以对初值极度敏感（他甚至生动描述过「一个极小的差异导致巨大后果」），是混沌思想的真正源头；20 世纪中叶的 KAM 定理则严格刻画了「规则区如何在扰动下幸存」。双摆正是这条思想脉络上最直观的物理玩具：**不需要三体，两根杆就够了。**

### 为什么数值方法不会「算错」，而只是「放大」

这是本项目最想澄清的一个误解。轨迹分道扬镳时，第一反应往往是「是不是积分器算错了？」——不是的，证据链有三条：

**1. 误差本身极小且规律。** RK4 每步截断误差 `O(dt⁵)`，双精度舍入 ~1e-16。测试 `test_convergence_order_is_fourth` 显示：步长减半，误差缩到 **1/16** —— 误差随步长按幂律干净地收敛，这是「算得准」的标志；若真是解错了，误差不会这么听话。

**2. 守恒量守得住。** 总能量 `E = T + V` 是自治系统的运动常数。demo 实测 10 秒 10000 步的相对漂移 **~5×10⁻⁹** —— 方程若推导有误，能量会系统性地漏掉，绝不可能贴着零线走。

**3. 放大的是「一切误差」，不只是数值误差。** 混沌系统对误差不加区分：数值截断的 1e-12、浮点舍入的 1e-16、测量仪器的 1e-9、甚至宇宙射线翻转的一个比特，都会按 `e^{λt}` 同样地指数放大。`d(t) = d₀·e^{λt}` 里没有「误差来源」这一项 —— **指数律本身不分青红皂白**。

所以正确的说法是：积分器忠实地算出了「从这个初值出发的那条轨道」，但**任何**轨道的邻居都会在几秒内被甩开。真实世界同理：测量精度再提高一百倍，也只是把分岔时刻推迟 `ln(100)/λ ≈ 2.3 s`，预测窗口的上限纹丝不动。Lorenz 当年正是由此得出「长期天气预报不可能」的结论 —— 不是计算机不够快，是问题本身没有长期确定性解。

一句话：**放大镜没有错，指数才是主角。**

---

## 数值方法与验证

- **RK4 定步长**：经典四阶 Runge–Kutta，局部 `O(dt⁵)` / 全局 `O(dt⁴)`；`integrate.Integrator` 基类留了 `step()` / `suggest_dt()` 两个变步长扩展位；
- **逐步快照**：每一帧记录 `t + 状态 + 能量 + 端点坐标`，能量序列直接喂给漂移图；
- **能量监测**：`E(t) - E₀` 作为数值质量的持续体检；
- **49 项测试**覆盖：单摆小角度周期 vs 解析解（实测误差 6.25e-6，正是理论非线性修正 θ₀²/16）、与教科书闭式解交叉对照、RK4 四阶收敛（ratio ≈ 15.8）、能量漂移上限、初值敏感性断言、静止边界能量为 0、SVG 合法性、动画帧数与退出逻辑。

---

## English Summary

A from-scratch double pendulum chaos simulator in pure Python standard library (no third-party dependencies). The equations of motion are derived from the Lagrangian in `pendulum/ode.py` and integrated with a fixed-step RK4 solver that records state snapshots and total energy at every step. The core demo integrates two initial conditions that differ by only 1e-4 rad: their phase-space distance grows exponentially (Lyapunov exponent λ ≈ 2/s) and crosses the divergence threshold at **t ≈ 2.0 s**, while total energy stays conserved to ~5e-9 relative — proving the trajectories separate because of dynamical amplification, not numerical error. Outputs include three hand-built SVG charts (overlapping time-graded trajectory comparison, energy drift, log-scale divergence curve) and a real-time terminal ASCII animation with non-blocking `msvcrt` input. 49 unit tests cover analytic period benchmarks, fourth-order convergence, energy bounds, and initial-condition sensitivity.

---

## Roadmap

- [ ] **Lyapunov 指数**：Benettin 两轨迹切线法（或每次分岔后重归一），量化 λ，输出「可预测时限」曲线 —— 把「感觉很乱」变成一个数；
- [ ] **变步长积分**：Dormand–Prince RK45，填上 `suggest_dt()` 扩展位，按局部误差自动调节步长；
- [ ] **相图吸引子**：Poincaré 截面（`ω₁ > 0` 时采样 `(θ₁-θ₂, ω₂)`），混沌区会显出分形层叠结构；
- [ ] **能量分区图**：扫描初始能量，画出规则区（KAM 环面）与混沌区的边界；
- [ ] **交互式调参**：标准库 `tkinter` 拖动滑块改初值，实时看轨迹分岔。

---

## License

MIT — 见 [LICENSE](LICENSE)。自由使用、修改、分发。
