# 全片统一 BGM 候选与来源

> 2026-11-06 选曲。全片约 4 分 15 秒（后续可能微增），需要**一首统一的纯器乐**垫在旁白下。
> 本文件只记录采购与试听信息，**不改动任何工程文件**。

---

## 一、选曲硬标准（本次执行口径）

- 纯器乐，绝对无人声 / 合唱采样（要压旁白）
- 厚重、克制、纪实：低音弦乐、钢琴、定音鼓、氛围 pad，政论纪录片 underscore 气质
- 不要史诗预告片 bombastic、电子舞曲、口水流行旋律、喜庆民乐合奏
- 动态友好：有平稳铺底段可压旁白，可带轻微起伏；避免大起大落的 drop
- 时长 ≥ 5 分钟（或结构简单可无缝循环）
- 授权可商用、可署名，优先 CC0，其次 CC-BY；必须记下作者 / 曲名 / 授权 / 来源 URL 供片尾标注

---

## 二、候选来源可达性（本次实测，2026-11-06）

| 来源 | 结果 |
| --- | --- |
| Pixabay Music | ❌ 直连超时（`pixabay.com` / `cdn.pixabay.com` 均 000，TCP 层被切断），无法直链下载 |
| Free Music Archive | ❌ 同样超时不可达 |
| FreePD.com（CC0 备选） | ❌ 站点已永久关站（2008–2025），首页只剩关站公告 |
| YouTube Audio Library | ❌ 需登录，按约定跳过 |
| **Scott Buckley（scottbuckley.com.au）** | ✅ **可达，CC-BY 4.0，电影感管弦 / 新古典，纪实向气质最对口** |
| incompetech（Kevin MacLeod） | ✅ 可达（`pieces.json` 曲目库 1443 首），作为备用库评估 |

最终三个候选**全部来自 Scott Buckley**，统一授权 CC-BY 4.0，片尾署名格式一致，最省事。
incompetech 已完整拉取评估（筛选结果见第五节），气质偏暗黑 / 悬疑 / 电子，纪实向铺底不如 Scott Buckley 贴。

---

## 三、候选清单（3 个）

试听段统一 90 秒，**覆盖「平稳铺底段 → 起伏段」**，首尾各加 1 秒淡入淡出，避免爆音。

### 候选 1（主推）：Memories Of Stone

- **曲名**：Memories Of Stone
- **作者**：Scott Buckley
- **授权**：CC-BY 4.0（可商用，需署名）
- **来源 URL**：https://www.scottbuckley.com.au/library/memories-of-stone/
- **气质一句话**：低音弦乐 + 铜管铺出「深时间」感，哀而不伤、克制厚重，像站在黄土沟壑前回望来路。
- **全曲时长**：330.3 s（5:30）
- **试听文件**：`assets/audio/bgm_cand_1.mp3`（90 s）
- **试听时间码**：全曲 `100s → 190s`
- **时间码依据**（ffmpeg `volumedetect`，20 s 窗口 mean_volume）：
  - 100–140 s：`-16.6 / -17.1 / -16.8 dB` —— 平稳铺底段，压旁白最干净
  - 160–180 s：`-15.5 / -15.7 dB` —— 弦乐渐起，进入第一处起伏
  - 全曲峰值区在 220–300 s（`-13.3 ~ -14.4 dB`），试听段刻意停在起伏**刚起来**的位置，不截大高潮
- **全曲文件**：`assets/audio/bgm_full_memories_of_stone.mp3`（12.6 MB，最终混音用）

### 候选 2：Within Our Nature

- **曲名**：Within Our Nature
- **作者**：Scott Buckley
- **授权**：CC-BY 4.0（可商用，需署名）
- **来源 URL**：https://www.scottbuckley.com.au/library/within-our-nature/
- **气质一句话**：钢琴 + 弦乐 + 合成 pad 的内省新古典，慢起、中段推起、末段回落，动态曲线最适合「铺底 + 一处起伏」的纪录片结构。
- **全曲时长**：399.3 s（6:39）
- **试听文件**：`assets/audio/bgm_cand_2.mp3`（90 s）
- **试听时间码**：全曲 `60s → 150s`
- **时间码依据**：
  - 60–100 s：`-20.4 / -18.7 / -19.6 dB` —— 开场铺底很「空」，旁白最易浮出
  - 120–150 s：`-16.5 / -15.9 / -15.7 dB` —— 明显渐强，给出起伏
  - 全曲最高点在 240 s（`-12.4 dB`），试听段只取到渐强的前半程
- **全曲文件**：未入库（体积考虑），需要时重取：
  `curl -L -o assets/audio/bgm_full_within_our_nature.mp3 "https://www.scottbuckley.com.au/library/wp-content/uploads/2022/11/WithinOurNature.mp3"`
  （若 404，到来源页 https://www.scottbuckley.com.au/library/within-our-nature/ 右键「Download MP3」取最新直链）

### 候选 3：Hiraeth

- **曲名**：Hiraeth
- **作者**：Scott Buckley
- **授权**：CC-BY 4.0（可商用，需署名）
- **来源 URL**：https://www.scottbuckley.com.au/library/hiraeth/
- **气质一句话**：氛围 pad + 弦乐 + 一把独奏大提琴的「回不去的故乡」，最轻最稳、最不抢旁白，乡愁底色贴「黄土高原 + 思政纪实」。
- **全曲时长**：346.2 s（5:46）
- **试听文件**：`assets/audio/bgm_cand_3.mp3`（90 s）
- **试听时间码**：全曲 `45s → 135s`
- **时间码依据**：
  - 45–70 s：`-17.1 / -16.7 dB` —— 稳定铺底
  - 80–135 s：`-15.1 / -14.9 / -15.0 / -14.9 dB` —— 大提琴旋律浮起，轻微起伏
  - 180–200 s 有一段回落（`-20.8 dB`），320 s 后进入淡出，均未纳入试听段
- **全曲文件**：未入库（体积考虑），需要时重取：
  `curl -L -o assets/audio/bgm_full_hiraeth.mp3 "https://www.scottbuckley.com.au/library/wp-content/uploads/2020/06/sb_hiraeth.mp3"`

---

## 四、片尾署名文本（直接可用）

三首统一格式，选定后照抄一行进片尾：

```
'曲名' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au
```

具体到本次候选：

```
'Memories Of Stone' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au
'Within Our Nature' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au
'Hiraeth' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au
```

> 若最终用于 YouTube，Scott Buckley 要求署名必须出现在**视频描述**中，否则会收到他的版权主张（可按其页面指引申诉移除）。

---

## 五、无人声核验说明

本次**无法人工试听**，无人声结论基于曲目页作者自述的配器清单交叉核对：

- Memories Of Stone —— 弦乐、铜管、Hardanger fiddle（无合唱 / 无人声）
- Within Our Nature —— 钢琴、弦乐、合成器（无合唱 / 无人声）
- Hiraeth —— 氛围 pad、弦乐、独奏大提琴（无合唱 / 无人声）

对照组：同库的 *This Too Shall Pass*（配器明写 choir）、*Light In Dark Places*（明写 choir）已在初筛阶段**直接排除**；incompetech 曲库中所有 `instruments` 字段含 `Vocal / Choir / Voice / Singer` 的曲目也全部排除。

**建议试听时重点确认这一点**（尤其候选 1 的铜管段是否有远处人声垫底），若有疑虑直接换候选 3（Hiraeth），配器最干净。

---

## 六、评估过但未入选的记录

**incompetech（Kevin MacLeod，CC-BY 4.0）** —— 曲库 `https://incompetech.com/music/royalty-free/pieces.json`（1443 首，含时长 / 配器 / feel 元数据），已按「时长 ≥ 5:00、无人声、feel 含 Somber/Dark/Calming、排除 Eerie/Humorous/Driving」筛出 59 条。气质最接近的三条：

| 曲名 | 时长 | 配器 | 不入选原因 |
| --- | --- | --- | --- |
| Long note One | 7:20 | Basses, Violins | 作者原话「a very long pad for use under dialog」，功能完全对口，但 feel 标注 `Intense / Suspenseful / Unnerving`，垫在纪实片里会发紧 |
| String Impromptu Number 1 | 6:14 | 弦乐群 | 「soaring and delicate」，起伏过大，压旁白会打架 |
| Sovereign | 6:12 | Piano | 暗色新古典独奏钢琴，厚度不够，缺低音弦乐与鼓 |

FreePD（CC0）已关站，Pixabay / FMA 网络不可达，故未纳入候选。

---

## 七、本目录文件清单

```
assets/audio/
├── BGM_SOURCES.md                    本文件
├── bgm_cand_1.mp3                    试听 · Memories Of Stone（90s）
├── bgm_cand_2.mp3                    试听 · Within Our Nature（90s）
├── bgm_cand_3.mp3                    试听 · Hiraeth（90s）
├── bgm_full_home_was_you.mp3         全曲 · 候选4（2026-11-07 补选）
└── bgm_full_memories_of_stone.mp3    全曲 · 主推（最终混音用）
```

---

## 八、补选候选4（2026-11-07 · 用户反馈现曲「抽象」后加选）

- **曲名**：Home Was You
- **作者**：Scott Buckley（2026-07-17 发布）
- **授权**：CC-BY 4.0
- **来源 URL**：https://www.scottbuckley.com.au/library/home-was-you/
- **直链**：https://www.scottbuckley.com.au/library/wp-content/uploads/2026/07/HomeWasYou.mp3
- **气质一句话**：钢琴 + 弦乐 + 手风琴 + 民间打击的乡愁民谣味，有清晰的节奏推进但不抢旁白，贴「黄土高原 / 乡土纪实」，与现曲的稀疏氛围感形成对照。
- **全曲文件**：`assets/audio/bgm_full_home_was_you.mp3`
- **署名**：`'Home Was You' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au`
- **排除记录**：Phoenix（2018 原版）配器明写 choir，违反无人声红线，不入选；Phoenix (2026) 室内弦乐版未取（URL 未确认，需要时再取）。

**效果样片（40s，旁白+候选按成品电平混）**：`output/bgm_demo/`
`0_current_memories_of_stone.wav`（现片基准）/ `1_within_our_nature.wav` / `2_hiraeth.wav` / `3_home_was_you.wav`
