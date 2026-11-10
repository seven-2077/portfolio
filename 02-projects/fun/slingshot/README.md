# 弹弓拆塔 · 弹弓物理 · Slingshot

愤怒的小鸟式弹弓物理游戏，**纯 Python 标准库零依赖**。

核心卖点一句话：**坍塌不是动画，是物理算出来的。**
没有预设的倒塌脚本——每次撞击后塔歪成什么样、哪根柱子先断、废墟堆成什么形状，
全由 Verlet 积分 + 迭代碰撞松弛逐帧算出，同一关重打十次，废墟十次都不同。

```
  ▐██▌                            撞击瞬间
   ██   ← 石块                   ╱    ▒  ← 木块飞散
  ▐▒▌▒   ← 玻璃柱              ●       ░  ← 玻璃碎屑
  ─────────────────────────────────────———
```

---

## 快速启动

环境：Python 3.10+，Windows / macOS / Linux 均可，无需安装任何第三方包。

```powershell
cd 02-projects/fun/slingshot

# 自动演示 3 关（预设发射参数脚本回放，实时终端渲染）
python demo.py

# 只看文字摘要（CI / 快速检查）
python demo.py --no-render

# 渲染但不等待帧间隔（快速过场）
python demo.py --fast

# 交互模式：自己打第 2 关，键盘输入角度和力度
python demo.py --play 2

# 其它开关
python demo.py --level 3        # 只跑第 3 关
python demo.py --fps 60         # 调整渲染帧率
```

交互模式下每发会提示：

```
 角度 55° (0-150): 58      ← 仰角，0=平射向右，90=垂直向上
 力度 80% (1-100): 94      ← 拉弓力度，决定出膛速度
```

回车即采用默认值。瞄准时会显示**虚线抛物线预演**（用与实射完全相同的
Verlet 步进跑出来的，不是解析公式敷衍），松手前就能预判落点。

跑完三关，`output/` 下会生成三张废墟矢量图：

```
output/level_1_result.svg   塔楼
output/level_2_result.svg   堡垒
output/level_3_result.svg   悬挑
```

跑单元测试（54 个）：

```powershell
python -m unittest discover -s tests
```

---

## 为什么用 Verlet

### 积分方案对比

最直白的物理积分是显式欧拉：\(v \mathrel{+}= a\,dt\)，\(x \mathrel{+}= v\,dt\)。
问题是**能量不守恒还漂**——堆个三层塔，每一层的数值误差互相放大，
几十步之后整摞方块开始肉眼可见地哆嗦，永远睡不着。

Verlet 换了个记账方式：**不存速度，速度是白送的**。

$$
x_{n+1} = x_n + (x_n - x_{n-1}) \cdot \text{damping} + a \cdot dt^2
$$

相邻两帧的位置差 \((x_n - x_{n-1})\) 本身就是速度（隐含速度 \(v = (x_n - x_{n-1})/dt\)）。
这个改写带来三个实打实的好处：

1. **速度不独立演化，误差不积累。** 位置差就是速度，速度永远"贴着"位置走，
   没有独立变量可以跑飞。静态堆叠放 100 步，位移是机器精度级别的近零
   （有测试盯着这个）。
2. **改速度 = 挪 prev 点，一等公民。** 碰撞响应要消除相对速度？
   把 `prev` 按同样方向挪一点就行，数学上等价于改写隐含速度，
   不会出现"改了速度忘了改位置"的撕裂。
3. **约束求解天然顺手。** 皮筋、绳子这类"两点距离固定"的约束，
   直接把两个粒子各拽回一半，迭代几轮就收敛——这就是高斯-赛德尔松弛，
   愤怒的小鸟的皮筋就这么实现的。

### 本项目的实现

`physics/verlet.py` 一共三个角色：

- `Particle`：位置 `(x, y)` + 上一帧位置 `(px, py)` + 加速度 + 质量，
  `set_velocity / velocity` 在隐含速度与 prev 之间互转，支持 `sleep()` 冻结。
- `DistanceConstraint`：两点距离约束，松弛时**同时挪 pos 和 prev**
  （纯搬运不注入虚假能量），支持 `one_sided=True`——
  **弹弓的两根皮筋就是它**：只抵抗拉伸，不抵抗压缩，所以拉弓时皮筋贴手、
  松开瞬间只受拉不受推。
- `step()`：显式积分 + 阻尼，固定步长 \(dt = 1/120\,\text{s}\)（120 Hz 物理）。

阻尼 `damping=0.998` 是故意留的数值刹车：每帧速度打 99.8 折，
等价于极弱的空气阻力，是堆叠能在几百步内彻底睡死的最后一公里。

---

## 碰撞：两段式响应

`physics/collision.py` 处理三种接触：**圆 vs 方块**（弹丸打结构）、
**方块 vs 方块**（结构自支撑）、**地面**。响应严格分两段：

### 第一段：位置分离

按逆质量比例把穿插深度摊掉（重的挪得少、轻的挪得多），
**pos 和 prev 同步平移**——这一步只搬运、不产生任何速度，
所以挤压时不会凭空弹开。

### 第二段：冲量近似

沿接触法线消除相对接近速度，外加切向库仑摩擦：

- 接近速度 \(|v_n| \ge 0.6\)：带轻微回弹（恢复系数 \(e = 0.10\)），
  慢慢砸是"啪"，快速砸是"嘣"；
- 接近速度 \(|v_n| < 0.6\)：**非弹性死停**（\(e = 0\)），
  把相对法向速度直接抹平、不回弹。静置接触走这条路，
  冲量小到远低于损伤阈值（见下节），方块不会被自己的体重磨死——
  这是堆叠能安睡而不是慢性自杀的关键；
- 摩擦 `μ = 0.45` 按 \(|\mu j|\) 夹紧切向冲量，压着的方块不打滑。

每步跑 **6 轮**碰撞松弛迭代（`COLLISION_ITERS = 6`），
一摞方块的接触链在同一步内就能传导到底，不会出现"下面的还没让开、
上面的又压下来"的滞后抖动。

---

## 材质与碎裂规则

`physics/structure.py` 定义三种材质，密度决定质量、耐久阈值决定脆度：

| 材质 | 密度 | 耐久 hp | 终端字符 | 一句话手感 |
|------|------|---------|----------|-----------|
| 木 `wood`  | 1.00 | 26 | `▒` | 中规中矩，一发能带走一整列 |
| 玻璃 `glass` | 0.55 | 8  | `░` | 轻且脆，擦一下就碎，分数也低 |
| 石 `stone` | 1.80 | 34 | `█` | 又重又硬，得正面怼才拆得动 |

**损伤模型**：单次碰撞的法线冲量 \(j\) 记入方块 `hp`：

- \(j < 1.0\)（`MIN_IMPULSE`）：微接触，**不计损伤**——静置、
  轻微沉降都不扣血；
- \(j \ge 1.0\)：`hp -= j`，hp 归零 → 方块**碎裂移除**，
  原地溅出 4~6 个碎块粒子（也走 Verlet，落地弹两下就静止）；
- 碎裂瞬间**唤醒全部邻居**（`_harvest` 里的连锁）：
  支撑柱一断，上面的横梁立刻重新参与结算，
  失去支撑就掉、砸到东西再碎——**这就是连锁坍塌的全部秘密**，
  没有任何"倒塌动画"，纯粹是每帧重新问一遍"你还被谁撑着"。

**休眠防抖**（`Dormancy`）：速度低于 \(0.45\) 单位/秒并持续 40 个物理步，
粒子进入 `sleeping` 状态——直接冻结积分，彻底不参与更新，
既防堆叠末端的微小抖动，也省 CPU。被大冲量（\(j > 0.8\)）或
明显穿透（深度 \(> 0.02\)）撞到时自动醒来。

---

## 得分规则

`game/scoring.py`：

- 破坏得分：木块 100 / 玻璃 60 / 石块 150（石块难拆所以分高）；
- 剩余弹丸奖励：每发未用的弹丸 **+400**——鼓励省子弹；
- 通关奖励：全拆完 **+500**；
- HUD 实时显示：关卡、得分、剩余弹丸、破坏计数、破坏率。

三关全自动演示的基线成绩（`python demo.py --no-render`）：

```
关卡1 塔楼   ：破坏  7/7 (100%) · 1480 分 · 弹丸 2/3
关卡2 堡垒   ：破坏  9/9 (100%) · 1480 分 · 弹丸 4/4
关卡3 悬挑   ：破坏  7/8  (88%) ·  680 分 · 弹丸 3/3
总得分 3640 · 平均破坏率 96%
```

---

## 关卡格式教程

关卡放在 `levels/levelN.json`，纯 JSON，任何文本编辑器都能改。
完整示例（`levels/level1.json`，塔楼）：

```json
{
  "name": "塔楼",
  "world": { "width": 96, "height": 32, "gravity": 30 },
  "ground_y": 28,
  "sling": [10, 24],
  "ammo": 3,
  "blocks": [
    { "x": 58, "y": 26, "w": 1, "h": 4, "material": "wood" },
    { "x": 64, "y": 26, "w": 1, "h": 4, "material": "wood" },
    { "x": 61, "y": 23.5, "w": 8, "h": 1, "material": "wood" },
    { "x": 59.5, "y": 21.5, "w": 1, "h": 3, "material": "glass" },
    { "x": 62.5, "y": 21.5, "w": 1, "h": 3, "material": "glass" },
    { "x": 61, "y": 19.5, "w": 5, "h": 1, "material": "wood" },
    { "x": 61, "y": 18.5, "w": 1, "h": 1, "material": "glass" }
  ]
}
```

字段说明：

- **坐标系**：原点在左上角，**y 轴向下**，单位是世界单位（1 ≈ 1 格）。
- `name`：关卡名（HUD 和 SVG 标题会显示）。
- `world.width / height`：世界尺寸（宽 ≥ 40，高 ≥ 20）；
  `world.gravity`：重力加速度，默认 30，必须在 (0, 200]。
- `ground_y`：地面线的 y 坐标，方块底边不能越过它。
- `sling`：弹弓锚点 `[x, y]`，必须在世界内且高于地面，
  也是弹丸出生点（不能贴着方块）。
- `ammo`：弹丸数 1..9。
- `blocks[]`：每个方块用**中心点 + 宽高**描述，
  `material` 只能是 `wood` / `glass` / `stone`，
  尺寸 (0, 20]，单关最多 60 块。

**合法性校验**（`game/level.py::validate`，加载时自动执行，
不过就报错拒载，错误一次列全）：

1. 字段齐全、类型正确、数值范围合法；
2. 方块不超出世界左右边界、不越过地面线/顶部；
3. **两两不重叠**（重叠即报错）；
4. **不悬空**：每个方块底边必须贴地、或贴在某个方块的顶边上
   （悬挑结构靠这个校验——横梁压在柱头上是合法的，飘在半空不行）；
5. 弹弓锚点/出生点不与任何方块冲突。

内置三关正好覆盖三种结构类型：

- **关卡 1 塔楼**：双木柱 + 横梁 + 玻璃芯，正面一发入魂；
- **关卡 2 堡垒**：石板屋顶 + 多材质混搭，需要挑脆的地方打；
- **关卡 3 悬挑**：悬臂梁结构，打断支点整段塌落。

想加第四关？复制 `level1.json` 改名字存成 `level4.json`，
`python demo.py` 没有预设参数时可以先用 `--play 4` 手打试结构。

---

## 代码结构

```
slingshot/
├── physics/
│   ├── verlet.py        # Verlet 积分器、距离约束（皮筋/绳）
│   ├── collision.py     # 圆-方、方-方、地面：分离 + 冲量 + 摩擦
│   └── structure.py     # 三材质、耐久碎裂、连锁唤醒、休眠
├── game/
│   ├── level.py         # JSON 关卡加载 + 合法性校验
│   ├── world.py         # 固定步长主循环（120Hz，6 轮碰撞松弛）
│   ├── sling.py         # 拉弓、皮筋约束、抛物线轨迹预测、发射
│   ├── render.py        # 终端字符画渲染 + SVG 废墟图导出
│   └── scoring.py       # 得分规则
├── levels/              # level1~3.json（塔楼/堡垒/悬挑）
├── tests/               # 54 个单元测试（7 个文件）
├── output/              # 运行 demo 生成的 SVG 废墟图
├── demo.py              # 自动演示入口
├── LICENSE              # MIT
└── README.md
```

核心代码约 1030 行（physics 345 + game 684），加 demo 入口共约 1210 行。

**测试覆盖**（`python -m unittest discover -s tests`，54 个全绿）：
Verlet 抛物线 vs 解析解对照、约束松弛收敛、碰撞无穿插、
堆叠静止 100 步位移近零、材质碎裂阈值、连锁坍塌、
弹弓轨迹预测与实射一致、关卡合法性（合法/悬空/重叠）、
SVG 可解析、得分规则。

---

## English Summary

An Angry-Birds-style slingshot game in **pure Python standard library**
(Python 3.10+, zero dependencies, Windows-friendly). The collapse is
*computed, not animated*: every ruin shape falls out of a Position Verlet
integrator (`x += (x - x_prev)·damping + a·dt²`), iterative constraint
relaxation for the rubber bands, and a two-phase collision resolver
(position separation + normal impulse with Coulomb friction, run 6× per
120 Hz step). Three materials (wood / glass / stone) carry durability HP;
impulses above a minimum threshold chip damage away, and a block breaking
wakes all neighbors — that single rule produces full chain-reaction
collapses without any scripted animation. A sleep/dormancy system freezes
settled bodies so stacks stay rock-steady (verified by a 100-step
near-zero-drift test). JSON levels are validated for overlap and floating
blocks. `demo.py` replays three scripted levels, prints per-shot summaries,
and exports final ruin images as SVG to `output/`. 54 unit tests pass.

---

## Roadmap

- **更多材质**：冰（超脆、融化）、弹簧板（受击反弹）、 TNT 桶（爆炸冲量
  半径传播）——材质表是数据驱动的，加一行就生效；
- **风场**：世界级恒定加速度 + 阵风扰动，弹道预测自动纳入风偏；
- **双弹丸**：同屏两发（约束切换 + 独立生命周期），解锁二连击玩法；
- **关卡编辑器**：终端里摆放方块、实时校验合法性、一键导出 JSON；
- **更多破坏反馈**：SVG 导出加入撞击火花、屏幕震动参数、回放录像格式。

---

## License

[MIT](LICENSE)
