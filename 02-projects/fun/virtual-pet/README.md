# 电子宠物 · virtual-pet · 终端电子宠物（拓麻歌子式养成）

纯 Python 标准库写的小宠物：真实时间演化、状态机驱动、跨会话存档，
四段成长（蛋 → 幼年 → 成年 → 老年），ASCII 多帧形象。
还有一个彩蛋——**study-timer 的学习数据可以当「食物」**：学得多宠物长得好，摆烂它就蔫。

零依赖 · Python 3.10+ · Windows 可跑

---

## 快速启动

```powershell
cd 02-projects/fun/virtual-pet

python demo.py --snapshot             # ① 一键演示：时间加速跑一整天，日志 + 状态快照图
python -m pet.interact                # ② 交互游玩（1 喂食 2 玩耍 3 睡觉 4 详情 q 退出）
python -m unittest discover -s tests  # ③ 测试（65 个用例）
```

演示会输出 `output/day_log.txt` 文本日志；加 `--snapshot` 再生成
`output/day_snapshot.bmp` 状态快照图（手写 24-bit BMP，无第三方库）。

---

## 玩法

四条属性都是 0-100，外加年龄与成长阶段：

- **饱食**（内部叫 hunger，0=饱 100=饿）：8 小时不喂见底
- **心情**：10 小时无互动见底，玩耍能拉回来
- **能量**：清醒 16 小时耗尽，睡 5 小时回满；低于 15 拒绝玩耍
- **健康**：长期饥饿/耗能 → 下降；吃饱睡好 → 回升；≤30 就是生病

**时间模型**：状态只在 `advance()` 被调用时按时间戳增量结算，
关机期间的时间下次启动一次性补算——但有两层保护：

```
eff = min(实际间隔, 12h) × (间隔 > 2 分钟 ? 0.5 : 1.0)
```

即离线单次最多补算 12 小时、且打对折。**离线衰减上限**保证：
摆烂一周回来宠物会变差，但绝不会瞬间病危、更不会一觉醒来直接老年。

---

## 状态机设计

状态集合：`idle | eating | playing | sleeping | sick`

### 玩家输入侧（动作转移）

```
idle ──feed──→ eating ──10s 结算──→ idle        饱食↑ 心情↑（学习加成放大）
idle ──play──→ playing ──15s 结算──→ idle       心情↑ 能量↓（-15 能量开销）
idle ──sleep──→ sleeping ──睡满/叫醒──→ idle    能量持续恢复

守卫条件（拒绝执行并给出理由）：
  play  ✗ 能量 < 15（太累了）   ✗ 睡觉中   ✗ 生病中
  feed  ✗ 睡觉中（先叫醒）      sleep ✗ 吃饭中
```

### 时间演化侧（advance 结算驱动的转移）

```
                    advance(now)
        ┌───────────────────────────────────────┐
        │  饱食下降(变饿)  心情下降  年龄增长     │
        │  睡觉中：能量恢复   醒着：能量消耗      │
        │                                        │
        │  压力模型（stress_seconds）：           │
        │   饥饿 ≥ 阶段警戒线 或 能量 = 0        │
        │        → stress 累积（封顶 2h）         │
        │   否则 → stress 衰减；喂食直接清 1h     │
        │                                        │
        │   stress ≥ 1h ──→ health 下降（4h清零） │
        │   stress <  1h 且吃饱睡够              │
        │        ──→ health 回升（4h 回满）        │
        └───────────────────────────────────────┘

idle    ── health ≤ 30 ──→ sick    「生病了」（每场病只播报一次）
sick    ── health ≥ 45 ──→ idle    「康复了」
eating / playing / sleeping 结束时 health ≤ 30 ──→ 直接回 sick（不重复播报）
```

### 成长阶段（年龄 + 健康双门槛，一次只晋一级）

```
阶段   最小年龄   饥饿警戒线   形象
────────────────────────────────────────
蛋      0h          95        会眨眼的彩蛋
幼年    1h          85        毛茸茸小鸡样
成年    6h          80        圆润大猫样
老年    10h         70        白胡子拄拐杖

晋升条件：age ≥ 下一阶段 AND health ≥ 50
  → 健康不足时事件提示「营养不足，迟迟长不成…」，阶段停滞但绝不降级
  → 各阶段警戒线不同：越老越容易饿出病
```

---

## 彩蛋：用学习数据养宠物

宠物每顿饭的分量，取决于你今天学了多久。

**约定接口（只读，绝不写入）**：优先读 study-timer 的记录文件

```
04-tools/study-timer/data/log.json
    [ {"start": "2026-11-05T09:00", "end": "...", "minutes": 90.0,
       "subject": "408", "note": ""}, ... ]
```

**换算规则**：统计 `start` 为今天的条目 `minutes` 总和，按 4 小时目标线性折算：

```
加成 = min(今日分钟 / 240, 1) × 50%          # 最多 +50%
喂食时：饱食 +35 × (1 + 加成)，心情也有额外加成
```

界面顶部常驻显示：

```
 📚 今日学习 5h00m（演示数据）→ 喂食加成 +50%
 📚 今日学习 3h30m → 喂食加成 +36%（study-timer）
```

**回退策略**：文件不存在 / 损坏 / 字段缺失 → 自动改用内置演示数据
（300 分钟，+50%），界面标注「演示数据」，游戏不中断。

**改路径**：`pet/studylink.py` 顶部的 `STUDY_DIR` / `LOG_FILE` 常量；
换算参数是 `DAILY_TARGET`（240 分钟）与 `MAX_BONUS`（0.5）。

---

## 项目结构

```
virtual-pet/
├── pet/
│   ├── engine.py      # 状态 + 真实时间演化 + 状态机（核心）
│   ├── growth.py      # 四段成长：年龄阈值 / 健康门槛 / 阶段属性
│   ├── sprites.py     # ASCII 形象：多帧眨眼 × 心情四档 × 睡姿
│   ├── persist.py     # JSON 存档：往返 / 损坏备份 / 坏值夹取
│   ├── interact.py    # 终端交互：msvcrt 非阻塞 + 非 TTY 演示模式
│   └── studylink.py   # 彩蛋：读 study-timer 学习数据 → 喂食加成
├── tests/             # 65 个用例（7 个测试文件）
├── demo.py            # 一键演示：时间加速一天 + BMP 快照
├── output/            # demo 产物（day_log.txt / day_snapshot.bmp）
├── data/              # 存档 pet.json（不入库）
├── README.md  LICENSE  .gitignore
```

---

## English Summary

A zero-dependency Tamagotchi-style terminal pet in pure Python (3.10+).
Pet stats (fullness, mood, energy, health) evolve through **timestamp-based
incremental settlement**: offline time still counts, but is capped at 12h per
catch-up tick and halved beyond a 2-minute grace window, so neglect hurts
without ever killing the pet instantly. A finite state machine drives
`idle → eating / playing / sleeping / sick` transitions with guard conditions,
and four growth stages (egg → baby → adult → elder) unlock by age **and**
health. Saves are plain JSON with graceful corruption fallback (the broken
file is backed up as `.corrupt`). A `studylink` easter egg reads your
study-timer `data/log.json` **read-only** and converts today's study minutes
into a feeding bonus (up to +50%): study more, pet grows better.
65 unit tests; `python demo.py --snapshot` simulates a full day in seconds.

---

## Roadmap

- **更多互动**：散步、洗澡、训练小游戏、心情礼物与护理道具，异常状态细分（受伤/着凉）
- **多宠物**：领养第二只、宠物间串门，存档升级为多槽位
- **图形化**：TUI 半图形界面（更大像素画、动画帧率），或导出 GIF/分享卡片
- **study-timer 深度联动**：连续打卡孵化稀有装饰、当日未达标第二天饿得更快
- **分享导出**：存档导出为可分享的宠物名片（文本海报）

---

## 开发备忘

- 测试：`python -m unittest discover -s tests`（时间戳全部注入，可复现）
- 存档：`data/pet.json`，损坏时自动备份为 `data/pet.json.corrupt`
- License: MIT（见 `LICENSE`）
