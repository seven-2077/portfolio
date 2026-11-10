# 迷宫射线射击 · raycast-fps —— 终端伪 3D 迷宫射击

字符终端里跑起来的 Wolfenstein 3D：**每帧给屏幕的每一列各投一条射线**，
把网格地图里的墙"立"成一圈会随你转头而变化的立体迷宫，边走边开枪，清光敌人通关。

与 [`02-projects/fun/raytracer`](../raytracer)（离线光线追踪）是姊妹作——
同一套几何思想，一个在离线里追求画质，一个在实时里追求帧率。

```
 ------@@@@@@                                                        @@----@@@@@@
-#################                                               @@@@@----@@@@@@
-#################                                            @@@@@@@@----@@@@@@
-#################@%                                        %@@@@@@@@@----@@@@@@
-########@...#....@%%%%-%%                            %-%%%%%@@@@@@@@@----@@@@@@
-########.##.#.###@%%%%-%%%%%                      %%%%-%%%%%@@@@@@@@@----@@@@@@
-########.#..#.#..@%%%%-%%%%%%#                 ##-%%%%-%%%%%@-@@--@------------
-########...#..#..-----------%:+++++++::+++++++#::------------------------------
-----------@-@@----%--%--%-%%-#:::::::::::::::::##-%--%--%----@@-@@-@-----------
@@@@@@@@@@@@@@@@--@%%%%%%%-%%%#::++++++++++++::###%%-%%%%%%%--@@@@@@@@@@--@-@@-@
@@@@@@@@@@@@@@-@---------                              ---------@-@@@@@@@@@@@---
@@@@@@@---------                                                ---------@@@@@@@
 HP[==========]100 AMMO 24 SCORE 00000 敌 3/3 FPS  30.0 地图 开
[WASD]移动 [←→/JL]转头 [空格]开火 [M]地图 [Q]退出
```

## 快速启动

要求 Python 3.10+，纯标准库零依赖，Windows / macOS / Linux 均可。

```bash
cd 02-projects/fun/raycast-fps

python demo.py            # 交互模式：直接开玩
python demo.py --demo     # 自动巡游：预录输入走完地图并开枪，帧序列录到 output/
python demo.py --demo --map random --seed 7      # 换随机迷宫
python demo.py --demo --map vault --show         # 实时观看巡游（限速 30fps）

python -m unittest discover -s tests             # 单元测试（120 条）
```

交互模式建议把终端放大到至少 80×24；窗口小于 32×8 会直接提示。

## 操作

| 按键 | 动作 |
|------|------|
| `W` / `S` | 前进 / 后退 |
| `A` / `D` | 左右平移（ strafe ） |
| `←` `→` 或 `J` / `L` | 转头 |
| `空格` / `F` | 开火（准星 hitscan，冷却 0.25s） |
| `M` | 小地图开关 |
| `Q` / `Esc` | 退出 |

胜负：**场上 3 个敌人全部消灭 = 通关**；血量归零 = 失败。脚踏上出口格另有一笔 50 分奖励。
弹药（+12）与医疗包（+30）散在迷宫里，枪声会惊动 9 格内的敌人。

## Raycasting 原理：一列射线怎么变成一面墙

### 1. 每列一条射线，DDA 沿网格"跳格子"找交点

屏幕宽 80，就投 80 条射线。对第 `x` 列，把列位置换算成相机空间里的水平偏移
`cam = 2(x+0.5)/width − 1`，再合成射线方向 `ray_dir = dir + cam · plane`。

求"射线撞到哪面墙"不用傻傻地一小步一小步试探，而是 **Amanatides & Woo 的网格 DDA**：
射线斜率决定了它穿过每一条竖格线 / 横格线的步长 `delta_x, delta_y`，每次只跳到
**下一条格线**，落在哪格就查哪格是不是墙——跨越整张地图最坏也就几十次跳，
每列 $O(\text{格数})$，而且天然知道撞的是东/西墙还是南/北墙（`side`）。

```text
        ┌───┬───┬───┐
        │ · │ · │ · │          side_x        side_y
        ├───┼─·─┼───┤   ──▶  ◆──▶──▶──▶  ┌─▶──▶  只在跨格线时
  起点→·│   │   │   │        每步 +delta_x  │ +delta_y   才 step 一次
        ├───┼───┼───┤                      │
        │ · │ · │█ ←─┘ 第一个非空格 = 命中   ▼
        └───┴───┴───┘
```

### 2. 鱼眼校正：斜着量的距离要把"余弦"乘回来

射线撞墙的欧氏距离 `d` 是**沿视线方向量的斜边**，屏幕边缘的射线更斜、量出来更长，
一圈平墙会被画成弯的。乘上射线与视线夹角的余弦，换成**垂直距离**：

$$d_{\perp} = d \cdot \cos(\theta_{\text{ray}} - \theta_{\text{player}})$$

（DDA 实现里等价于直接累加 `perp_wall_dist`，数学上是同一回事。）

### 3. 垂直距离 → 墙的高度

透视投影里，物体的屏幕高度与深度成反比：

$$\text{墙的列高} = \frac{\text{视图高度}}{d_{\perp}}$$

`d_perp` 越大画得越矮，`wall_top = center − h/2`、`wall_bottom = center + h/2`
逐列填进帧缓冲——80 列拼起来，一圈平直的墙就"立"起来了。

### 4. 距离与朝向 → 明暗，墙面纹理按列采样

- **距离衰减**：亮度系数 `1.05 − 0.072·d`（下限 0.06），越远越暗；
- **朝向修正**：南/北面（`side=1`）再乘 0.72，正对你的墙更亮，一眼分清进深；
- **材质底图**：砖、石、金属板三种材质各是一张 `0-9` 亮度字符图案，
  用命中点在墙面上的横坐标 `wall_x` 取一列，再按纵坐标取纹素；
- 材质亮度 × 距离系数落进明暗表 `" .:-=+*#%@"`，得到最终字符。

### 和 raytracer 的关系

两者共用同一套几何（射线、交点、材质、明暗），分歧在**预算**：

| | raytracer（姊妹作） | raycast-fps（本作） |
|---|---|---|
| 射线数量 | 每像素数百条（抗锯齿、多次采样） | **每像素 1 条，每帧 80 条** |
| 求交方式 | 通用三角形/球体求交 | 网格 DDA，跳格子 $O(1)$/格 |
| 弹射次数 | 反射、折射递归多次 | 0 次（不反射，只打一面墙） |
| 时间预算 | 离线，跑几分钟 | **实时，16ms 内必须出一帧** |

一句话：raytracer 用无限时间换一张好看的图，raycast-fps 把同样的几何压进 30fps 的帧预算里。

## Sprite：画家算法 + z-buffer 遮挡

敌人和道具不是墙，用**精灵贴图**画：把世界坐标用相机矩阵的逆变换变到相机空间
`(tx, ty)`，屏幕横坐标 `width/2 · (1 + tx/ty)`、高度按 `1/ty` 缩放——和第 3 步的墙是同一个透视除法。

两层保证画得对：

1. **画家算法**：所有精灵按距离**从远到近**排序，远的先画、近的后画覆盖上去；
2. **逐列 z-buffer**：渲染墙面时顺手记下每一列墙的垂直距离 `zbuf[x]`，
   精灵某列的深度大于 `zbuf[x]` 就跳过——躲在墙后的敌人一笔都画不出来。

AI 两种：**哨兵**（巡逻型）沿固定方向走、撞墙顺时针换向；**猎杀者**（追踪型）看见你就直线扑，
隔墙就 BFS 找路绕过来。开枪的枪声会把 9 格内的敌人惊动。

## 架构

```
                     预录脚本 / msvcrt 非阻塞读键
                                │
                     ┌──────────▼──────────┐
                     │  player.py          │  移动（圆 vs 网格碰撞 + 贴墙滑动）
                     │  动作集 keys→actions │  转头、小地图渲染
                     └──────────┬──────────┘
                                │ Player(x, y, θ)
        ┌───────────────────────▼───────────────────────┐
        │ raycaster.py        每列一条射线               │
        │  · DDA 求交（撞哪面墙 / wall_x / 材质）        │◄──── fps/map.py
        │  · 鱼眼校正 → 垂直距离 → 墙高                  │      网格地图 · 校验
        │  · 距离明暗 + 纹理按列采样                     │      圆碰撞 · 视线 · 随机生成
        └───────────────────────┬───────────────────────┘
                                │ 逐列 zbuf[x]
        ┌───────────────────────▼───────────────────────┐
        │ sprites.py                                    │
        │  · 相机矩阵逆变换投影                          │
        │  · 画家算法排序 → 逐列 z-buffer 遮挡裁剪        │
        │  · 巡逻 AI / BFS 追踪 AI / 拾取物              │
        └───────────────────────┬───────────────────────┘
                                │
        ┌───────────────────────▼───────────────────────┐
        │ combat.py        准星 hitscan（角半径判定）     │
        │  · 命中 / 击杀 / 弹药 · 血量 · 胜负 / 出口      │
        └───────────────────────┬───────────────────────┘
                                │
        ┌───────────────────────▼───────────────────────┐
        │ loop.py                                      │
        │  · FrameBuffer：整帧先在内存拼成一个字符串      │
        │  · 一次 stdout.write（\x1b[H 覆盖）= 无闪烁    │
        │  · HUD / 帧率显示 / 限速 / 输入源抽象           │
        └───────────────────────┬───────────────────────┘
                                │
                    demo.py（巡游脚本录制 → output/）

文件树
raycast-fps/
├── fps/
│   ├── raycaster.py   DDA 射线投射 · 鱼眼校正 · 明暗与纹理（160 行）
│   ├── map.py         地图解析校验 · 碰撞 · 视线 · 随机生成器（389 行）
│   ├── player.py      移动转向 · 键盘读取 · 小地图（185 行）
│   ├── sprites.py     投影 · 排序遮挡 · 敌人 AI（321 行）
│   ├── combat.py      hitscan 命中 · 伤害 · 胜负（118 行）
│   └── loop.py        帧缓冲 · HUD · 主循环限速（269 行）
├── tests/             7 个文件 · 120 条用例
├── demo.py            交互 / 自动巡游双模式入口（210 行）
├── output/            巡游录制：demo_frames.txt / preview / summary
├── README.md · LICENSE · .gitignore
```

## 测试

```bash
python -m unittest discover -s tests     # 120 条，全绿
```

覆盖了关键的"数学对不对"：

- **DDA vs 几何法**：多角度多地图，网格步进距离与解析求交逐点对照；
- **鱼眼校正**：正对平墙时欧氏距离随列变化、校正后垂直距离处处相等；
- **纹理列采样 / 明暗**：`wall_x`→列号、纵坐标→纹素、距离衰减与朝向压暗；
- **碰撞边界**：四面撞墙不穿、贴墙滑动保留自由轴、对角切入墙角不越线；
- **sprite**：投影几何、远→近排序、z-buffer 逐列遮挡、巡逻撞墙换向、BFS 绕障逼近；
- **命中判定**：瞄准容差边缘、隔墙失效、最近目标优先、弹药耗尽拒射；
- **随机地图**：50 个种子全部合法连通、材质 ≥3 种、种子可复现；
- **帧缓冲与主循环**：越界裁剪、整帧拼接结构、预录输入节拍、HUD、胜负冻结。

## Demo 巡游

`python demo.py --demo` 按预录输入序列（约 40 段，30Hz 步进）自动走完 crypt 地图：
穿走廊、捡补给、踏上出口、开火清敌，最后转身清扫收尾。最新一次实测：

```
地图          crypt（16×15）      渲染帧数      1192
实际耗时      3998 ms             实测帧率      298.1 fps（纯渲染吞吐，无 sleep）
模拟时长      39.7 s @ 30 Hz      探索覆盖      66/117 格（56.4%）
击杀          3/3                 出口          已抵达
剩余血量      20                  最终得分      530
结局          通关
```

完整帧序列写在 `output/demo_frames.txt`（每帧以 `===== FRAME n =====` 分隔），
`demo_preview.txt` 是抽帧预览，`demo_summary.txt` 是上面这份统计。
性能远超"中端机 ≥20fps"的目标：**80×24 一帧约 3.4ms**。

## English Summary

A Wolfenstein-3D-style pseudo-3D maze shooter that runs entirely in the character
terminal. Pure Python standard library (3.10+), zero dependencies, cross-platform.

Each frame casts **one ray per screen column** using the Amanatides & Woo grid DDA,
converts hit distance to a perpendicular distance (fisheye correction), maps it to a
wall column height and a luminance character from a distance falloff ramp, and
samples per-column wall textures for three materials. Sprites (patrol / chase AIs
and pickups) are projected with the camera-matrix inverse, sorted back-to-front
(painter's algorithm) and clipped per-column against the wall z-buffer. Combat is
hitscan-based with angular-radius aiming; the frame is assembled in an in-memory
buffer and flushed with a single write to avoid flicker. Includes two handcrafted
maps plus a seeded maze generator, a scripted auto-tour demo that records text
frames to `output/`, and 120 unit tests — `python -m unittest discover -s tests`.

Sister project of `fun/raytracer`: same geometry, offline vs. real-time budget.

## Roadmap

- **更多敌人 AI**：远程射击怪（视线内风筝）、包抄型（两只猎杀者一前一后）、警戒值与巡逻路线可视化
- **武器系统**：霰弹枪（扇形 hitscan）、机枪（连发与过热）、枪口火花与命中闪白
- **门与钥匙**：推门动画、锁门与钥匙碎片、开门机关改变迷宫连通性
- **真贴图**：墙面多字符纹理（每格 2×4 字符）、地板/天花板透视填充、出口的动态图案
- **手感与外设**：鼠标视角（Windows 控制台鼠标事件）、手柄、灵敏度设置
- **关卡与存档**：多关卡串联、逐关计时与星级、随机地图难度参数

## License

[MIT](LICENSE) © 2026 Seven
