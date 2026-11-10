# hyperframe · 视频工程包

> 「足迹里的思政课」影像作品项目（甘肃足迹）——把视频当成 AI agent 可以编写和渲染的工程。
>
> **本文件是方法总纲。新会话的 agent 先读完本文件，再动任何其他文件。**

---

## 一、核心理念

把视频当成 AI agent 可以编写和渲染的工程：所有创作决策先沉淀进一组固定文件，agent 按文件干活，而不是凭印象即兴发挥。**不是只给一个想法，而是给一整套制作资料；文件越固定，AI 越少乱猜。**

这组固定文件就是下面的「六件套」。它们是全片唯一的事实来源（source of truth），口播、时间、画面、风格的一切改动都先改文件、再改代码。

## 二、固定资料包（六件套）

每件资料一个文件，职责单一、互不越界：

**01 口播稿 `SCRIPT.md`** —— 真正要说的口播稿，先定稿，别让 AI 改口播。它的作用是锚死内容边界：不让页面内容跑题。全片上游，一切时间与画面跟着它走。

**02 配音文件 `assets/audio/`** —— 口播稿定稿后录音。声音节奏决定画面节奏：先有声音，再排画面，而不是先剪画面再凑声音。

**03 字幕时间戳 `transcript.json`（或 `.srt`）** —— 告诉工程每句话、每个词大概什么时候出现；每句话出现在哪一秒。它是口播与画面之间对齐的桥梁，分镜和字幕都以它为准。

**04 分镜 `STORYBOARD.md`** —— 每段口播对应什么画面、动画、素材。每一段口播一个条目，画面来源、动画动作、素材路径逐条写死。

**05 素材路径 `assets/`** —— 真实素材、截图、图像、录屏都按路径放好，本地文件清楚可引用。代码里只允许引用这个目录内的路径，不许临时外链。

**06 风格与验收 `DESIGN.md`** —— 视觉风格、主色、字体、字幕样式、不能出现的风格（例如具体到"深色科技感、主色、字体、字幕样式"这种粒度）；外加验收标准：色彩、字幕、动效，以及画面对口播、字幕不遮挡、节奏不过快。既是给 AI 的约束，也是交付前的检查清单。

## 三、制作流程（agent 干活顺序）

六件套有严格的依赖链，上游定稿才动下游：

1. `SCRIPT.md` 口播稿定稿 —— 人定，AI 只辅助起草，定稿后不许改
2. 录音 → `assets/audio/` 配音文件 —— 声音节奏决定画面节奏
3. `transcript.json` 字幕时间戳 —— 从录音对齐导出
4. `STORYBOARD.md` 分镜 —— 每段口播落到具体画面、动画、素材
5. `assets/` 素材收集入库 —— 路径清楚可引用
6. `DESIGN.md` 风格定稿 —— 主色、字体、字幕样式、禁忌、验收标准
7. 代码生成：**读文件 → HTML 搭结构 → CSS 定样式 → GSAP 做动画**
8. 渲染 → 按 `DESIGN.md` 验收标准逐条检查后交付

改动纪律：口播稿是上游。一旦改稿，配音、时间戳、分镜三处必须同步更新，否则画面对不上声音——这是本方法里唯一会翻车的地方。

### 与 HyperFrames 工程的映射

流程第 7 步的 HTML / CSS / GSAP，在本项目里对应 HyperFrames（HTML → 视频）的三层：

- **HTML 搭结构** = `index.html` composition：DOM 结构 + `data-*` 属性声明时序（轨道、片段、起止秒数），段落结构跟随 `SCRIPT.md` 的编号
- **CSS 定样式** = 字幕排版、版式、主色，全部以 `DESIGN.md` 为准
- **GSAP 做动画** = 一条 paused 的 GSAP timeline 驱动全片，动画必须 seek-safe（可拖拽预览）
- **渲染** = `npm run check` 联审通过后 `npm run render`

若走 HyperFrames 官方 workflow，它会额外生成 `BRIEF.md`（路由与工作流契约）——与六件套不冲突：BRIEF 管"用哪条工作流做"，六件套管"做的是什么"。

## 四、本项目参数（甘肃足迹）

**课程**：《习近平新时代中国特色社会主义思想概论》课程实践「足迹里的思政课」。实践期 11 月 2 日–13 日，第 12 周起在指定系统提交，形式任选其一，本项目走**影像视频**（4-6 分钟资料混剪纪录短片）。

**主题素材方向**（甘肃足迹，围绕公开资料挖掘）：定西脱贫（渭源元古堆村）、敦煌莫高窟文化保护、八步沙"六老汉"治沙、引洮工程吃水梦。叙事骨架：意象开场 → 引入 → 核心叙事一（脱贫）→ 核心叙事二（生态/文化）→ 意象过场 → 青年视角收尾（数据科学专业学生看数据变化）。

**素材红线（硬约束）**：

- AI 不生成领导人形象、不复原历史场景、不冒充实景与史实——涉及人物事件只用真实公开影像
- ComfyUI 只出"非史实"意象画面（片头、过场、片尾），且只走图像模型（本机 8GB 显存，不下载视频模型），动态感由 HyperFrames 运镜补足
- 主干永远是挖掘来的真实素材 + 真人旁白；AI 画面是点缀不是生命线
- 所有引用素材在片尾标注来源

**技术栈**：HyperFrames（HTML→视频）+ ComfyUI（仅意象静态图）+ Python matplotlib（数据图表）。

**可收缩性**：时间失控先砍 ComfyUI 意象段 → 再降级纯图表排版 → 最后保底剪映。主干是素材挖掘和旁白质量，工具是加分项。

## 五、本机环境与工具位置备忘（agent 干活前先看这里）

**ComfyUI 位置**（2026-11-05 实探，技能库旧记录 `D:\Software\project_ware\...` 已失效）：

- 主用秋葉版 0.30.2：`D:\Project Software\ComfyUI-aki\ComfyUI-aki-v3.2\ComfyUI`——本项目出意象图就用它，模型/LoRA 全在其 `models/` 下按架构前缀管理（SDXL / Flux 等）
- ⚠️ **启动方式（2026-11-06 实测教训）**：不可绕过启动器直接调 `python.exe main.py`（报 `ModuleNotFoundError: No module named 'encodings'`），须用秋葉启动器或其 `run_nvidia_gpu.bat`
- 3D 版：`D:\Project Software\ComfyUI-3D\ComfyUI`
- 入门工作流库：`D:\Project Software\ComfyUI-aki\入门工作流\ComfyUI_Workflows`
- comfyui-mcp：`D:\Project Software\Github\comfyui-mcp`

**HyperFrames 位置**（无全局安装，npx 即用即走）：

- CLI：npx 缓存 `C:\Users\Seven\AppData\Local\Temp\cursor-sandbox-cache\...\_npx\...\node_modules\hyperframes`（临时缓存，重装即刷新）
- 技能文件：`C:\Users\Seven\.claude\skills\hyperframes*`（9 件）+ `C:\Users\Seven\DeskBox\各种文件夹\AI技能库\03-Plugins\hyperframes\`
- 技能克隆仓库：`C:\Users\Seven\AppData\Local\Temp\hyperframes-repo\`
- 可参照工程：`02-projects/fun/emergence/`——0.9.15 固定版本、Edge 渲染、五项联审命令、workflow 技能装不上的替代路径全记录在它的 README

**emergence 项目踩坑经验（直接复用）**：

- **渲染必须用系统 Edge**（Chrome for Testing 下载被网络干扰）：

  ```powershell
  $env:HYPERFRAMES_BROWSER_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
  ```

- HyperFrames 固定 `0.9.15`（emergence 的 package.json 所用版本）；GSAP 与字体全部本地化到 `node_modules/`、`fonts/`，渲染零外网依赖
- `general-video` workflow 技能装不上（`raw.githubusercontent.com` SSL 干扰，ghfast / jsdelivr / skills add 三条 fallback 均不通）——按 route 契约用本地 core / creative / cli 技能等效执行
- 常用命令：`npm run check`（lint + runtime + layout + motion + contrast 五项联审）、`npm run render -- --output renders/xxx.mp4 --quality looks`

## 六、目录结构

```
hyperframe/
├── README.md          本文件：方法总纲（agent 先读）
├── SCRIPT.md          01 口播稿（上游，定稿后不许改）
├── STORYBOARD.md      04 分镜
├── DESIGN.md          06 风格与验收
├── index.html         HyperFrames composition（代码生成，依赖六件套）
├── package.json       HyperFrames 工程（固定版本，脚本随 emergence）
├── transcript.json    03 字幕时间戳（录音对齐后生成）
├── assets/            05 素材（audio/ 图像/ footage/ charts/ ai/）
├── renders/           渲染成片（交付物，不入库）
├── .hyperframes/      工程缓存（git ignore）
└── .gitignore
```

## 七、当前状态与断点（2026-11-07 22:20 · v4 终版交付）

### 最新：v4 终版（2026-11-07 22:15 重渲验收）

- **v4 成片**：`renders/gansu_footprint_v4.mp4`（320.07s / 5:20，1920×1280 视频全幅+底部200px字幕黑带，h264+aac，225.7 MB）
- 新增片尾演职员卡（312.06–320.06s，8s）：ComfyUI MOSS-Image 生成静态卡（`output/ending_card/ending_card_gansu_00003_.png`，甘肃主题：黄河金带+层叠塬+烽燧+细金线框，名单组长何谭昕/组员李安·梁日皓·唐子帆），HyperFrames DOM 动效化——自上而下 clipPath 揭示、金色光带扫过（screen 混合）、14 粒金尘漂浮、末1.06s 淡黑；音频 `build_mix.py` 加 `TAIL_S=8.0` 续 BGM 并尾2s淡出
- **验收四帧全过**（`output/spotcheck_v5/`）：t=266.9 数字卡+正确字幕、t=274.9 正确、t=304.9 麦田+pill-s5-9、t=312.6 卡片揭示动效进行中且字幕已清
- **重要教训（渲染管线）**：首渲 v4 出过「片尾卡盖住整个 S5 + 字幕乱序」的坏片——合成与 preview 活体均正常（`__hf.clipWindow` 窗口正确），坏因是**渲染残留/断点续跑混入旧状态帧**。以后每次渲染完必须抽帧验收（select+showinfo 拿真实 PTS），坏片直接整段重渲（约7.5min），勿信文件时间戳
- 渲染备查参数：`-w/--workers`（默认 auto6进程）、`--docker`（确定性渲染）、`--low-memory-mode`（锁1 worker）

### 已交付（v2 时期记录）

- **v2 成片（2026-11-07）**：`renders/gansu_footprint_v2.mp4`（312.07s / 5:12，1080p30 h264+aac，`--quality looks`，228.8 MB）
  - `npm run check` **0 error / 0 dead_stretch**；Craft 0 警告（原 9 条 line_unread 假警根治）、Layout 0 issues、Contrast 12/12 WCAG AA、Audio 0
  - 根因（读源码反推，非试错）：`craftAudit.ts` line_unread × `layout-audit.browser.js` `isClippedAway` 15 点 `elementFromPoint` 探测——全屏 `.caption-cue` 拦截命中测试，把带 clipPath 镜头下的文本误判为 clipped-away，只在字幕间隙被算到可读窗口。修复：字幕容器改底部带 `inset: auto 0 0 0; height: 26%`；`wipeIn` 与 `#media-s5-1` 擦除 tween 加 `clearProps: "clipPath"`（稳态不留裁切路径，文本退出探测路径）
  - 抽帧五点验收通过（`output/spotcheck/`）：t=30 新闻日期角标、t=80 信息板 count-up、t=136 让位拍1 原声访谈、t=210 竖屏让位拍2 柱状黑边不拉伸、t=306 片尾标题+来源条
  - 六条红线全落实：一行句级字幕条 / 数字独立信息帧 / 静态图换视频 / 让位拍原声+旁白让位 / 红蓝条新闻包装+斜切转场 / 单条 `mix_full.wav`
- **v1 成片**：`renders/gansu_footprint.mp4`（4:08，1080p，用户已验收画面结构与叙事）
- **配音定稿**：男声钟离 `assets/audio/male/S0–S5.wav`（总 282.56s，commit `1841716`；女声版保留在 `assets/audio/S0–S5.wav`）
- **素材库**：视频 12 支（cctv×2、xinhua p1/p2/ducao/xincun/kuxianshui/taohe、dha_285ku、babusha_suosuo、taohe_pengshui、chinanews 敦煌考察）+ 图片 12 张（2013 考察照为视频源灭失后的存档替代，永久保留）
- **音轨听译分析**：`assets/video/AUDIO_ANALYSIS.md`（commit `170f2d4`）——10 段素材声音类型 + 访谈窗口 + 混音规则
- **统一 BGM**：`assets/audio/bgm_full_memories_of_stone.mp3`（Scott Buckley《Memories Of Stone》CC-BY 4.0，出处见 `assets/audio/BGM_SOURCES.md`，commit `9a56c5c`）
- **工程**：`index.html`（六件套齐，17 镜 62 时序节点，v1 校验 0 error / 0 dead_stretch）

### 音频总装（已完成，产出已验收入位）

- **音频总装子任务** `f0fad543`（23:07 启动，60 分钟上限，约 00:07 自然收工）
  - 任务书：钟离整轨 + 两个让位拍（`xincun 0–12s` 种植户访谈、`p1` 现场讲话原声）+ 统一 BGM 分段压制 → 产出 `assets/audio/mix_full.wav`、`TIMELINE_V2.md`（下游时间轴圣经）、重算 `transcript.json`
  - **11-07 验收结果**：三项全部产出并入位——`mix_full.wav`（312.06s 整轨）、`TIMELINE_V2.md`、`transcript.json` v2（60 句 + 2 让位拍）

### 后续待办（v2 交付后剩余）

1. 用户抽看 `renders/gansu_footprint_v2.mp4` 整片，反馈微调点
2. （可选）lint 剩余 73 条结构提示：给 62 条 caption-cue 补 id、拆子composition——均不挡交付

### 视觉改版任务书要点（明日照此直接派发）

1. **一行字幕条**：固定底部单行，深色半透明 + 金描边 + 央视新闻下三分之一风格，字幕**随朗读逐句更新**（不是整段一次上屏），句内切词按需；时间戳用重算后的 `transcript.json`
2. **数字卡改独立信息帧**：`110 km / 87% / 3 cm / 21.7 万亩` 等不再浮在实拍画面上——搬到专用图文帧（独立画面帧），数字 count-up 动画保留
3. **静态图 → 视频**：按 `MANIFEST_batch6/7` 的落位建议替换（xincun 顶棚镜头、dha_285ku + chinanews 考察进敦煌段、suosuo/pengshui 进第五章）；敦煌段全视频化；2013 灯笼照保留（源灭失）
4. **让位拍画面**：p1/p2 竖屏素材做裁切/分屏适配，xincun 访谈拍用大棚镜头
5. **新闻包装**：红蓝条 / 日期戳 / 栏目角标 / 段间新闻式切角转场，主色 CRI red `#C8102E` + 深蓝，淡入淡出节奏按新闻包装调整

### 用户反馈红线（改版依据，勿违反）

- 字幕只要**一行**、随句更新，不整段倒屏
- 百分比/数字卡**不遮实拍**，放独立画面帧
- 尽量不用静态图片，优先新闻机构视频源
- **访谈段保留原声 + 旁白让位**；其余片段去原声、统一 BGM 覆盖（原片配乐会打架）
- 全篇**统一一条 BGM**，旁白段压 -18~-22dB、让位拍压 -28dB、纯画面段 -10dB
- 男声**钟离**定稿；转场与包装**参考新闻设计**
