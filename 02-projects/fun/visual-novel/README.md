# 终端视觉小说 · vn —— 终端文字冒险 / 视觉小说引擎

> 纯 Python 标准库 · 零依赖 · Windows / macOS / Linux 通吃
> **引擎与剧本分离**：引擎是代码，故事是纯文本 —— 会写字就能做游戏。

打字机逐字台词、选项分支、好感度条件跳转、多结局阈值判定、JSON 多槽位存档、历史回看、ANSI 配色场景框……全部装在一个 4 模块的小包里。

---

## 快速启动

```powershell
cd 02-projects/fun/visual-novel

# 1. 自动演示：全程自动选第 1 项，跑完一条真结局路线
python demo.py                    # 带打字机节奏，全程文本写入 output/playthrough.txt
python demo.py --instant          # 跳过节奏，瞬间出产物
python demo.py --play             # 交互试玩（回车继续、输入选项编号）

# 2. 跑测试（114 个用例）
python -m unittest discover -s tests
```

交互模式可用的命令，在任意「继续」提示处输入：

| 命令 | 作用 |
|------|------|
| `⏎`（回车） | 继续下一句 |
| `s N` / `l N` | 存到第 N 槽 / 从第 N 槽读档（存档在 `output/saves/`） |
| `h` | 历史回看 |
| `+` / `-` | 打字速度加 / 减 |
| `q` | 退出本局 |
| 打字时按任意键 | 立即显示整句 |

其他开关：`--cps 60` 调速度、`--no-color` 关配色、`--script 路径` 换剧本、`--out 路径` 换产物位置。

---

## 剧本格式完整教程

剧本是 UTF-8 纯文本，建议扩展名 `.vn`，放在 `story/`。一行为一种东西，按前缀区分；空行与 `#` 开头的整行注释会被忽略（行内注释不支持，因为台词里常有 `#`）。

### 1. 台词与旁白

```text
澪: 今天…你也在啊。          ← 说话人: 台词（第一个半角冒号分隔）
|窗外的雨还没有停。          ← 旁白（| 开头，没有说话人）
我: 台词里有冒号的话\: 转义。 ← 半角冒号要写 \:
```

- 说话人可以用任何名字（`澪`、`我`、`广播`……），会渲染成黄色名牌。
- 中文冒号 `：` 可以直接写，只有半角 `:` 是分隔符。

### 2. 场景切换

```text
@scene 放学后的教室
```

渲染一个青色边框的场景标题框，同时记入历史（回看时能看到场景线索）。

### 3. 变量与好感度（@set）

```text
@set affection += 2        ← 加好感
@set affection -= 1        ← 扣好感
@set knows_truth = 1       ← 置标记
@set name = "澪"           ← 字符串（含空格或冒号必须加双引号）
@set mood = 晴             ← 裸词也行（无空格时）
@set ok = true             ← 布尔
@set score = 3.5           ← 小数
```

- 变量无需声明，未定义时读出来是 `0`，所以好感度直接 `@set affection += 1` 开始攒即可。
- **好感度就是常规变量 `affection`**，没有特权；引擎只是常用它做结局阈值。
- 值只能是数字 / 布尔 / 字符串（要能存进 JSON）。

### 4. 跳转与条件（@label @jump @if）

```text
@label start               ← 定义标签
@jump start                ← 无条件跳转

@if affection >= 3 -> warm_path        ← 满足条件才跳
@if knows_truth == 1 and courage >= 1 -> true_end
@if affection >= 5 or flag == 1 -> any_path
```

条件表达式的写法：

- 比较符：`==`、`!=`、`>`、`>=`、`<`、`<=`
- 连接词：`and`、`or`（`and` 优先于 `or`，从左往右算；不支持括号）
- 右值三种形态：数字（`3`）、加引号的字符串（`"晴"`）、**不加引号的标识符 = 引用另一个变量**（`@if affection >= mood`）
- 未定义变量按 `0` 参与比较

### 5. 选项分支（@choice）

```text
@choice
- 走过去，把纸巾递给她 -> c1_tissue
- 装作没看见 -> c1_ignore
- [knows_truth == 1] 「这次我陪你」 -> c1_with   ← 条件选项，不满足时隐藏
```

规则：

- `@choice` 之后所有以 `- `（减号 + 空格）开头的行都是选项，遇到第一个非选项行就结束选项块。
- 每个选项必须写 `-> 标签`；文本里避免出现 `->` 字样（箭头可用 `→`）。
- 方括号里的条件不满足时该选项**不显示**；请至少留一个无条件选项兜底，否则运行时报错。
- 交互时空回车 = 选第 1 项；自动演示（`demo.py`）永远选第 1 项。

### 6. 结局判定（@end @ending）

```text
@ending 一起去看海 when affection >= 5 and knows_truth == 1   ← 阈值规则
@ending 天台上的约定 when affection >= 3
@ending 普通的放学路 when affection >= 1

...故事内容...
@end                      ← 结束：按上面的规则自上而下取第一个命中
@end 直接指定的结局        ← 结束：不走阈值，直接指定结局名
```

- 规则写在剧本任意位置（一般放开头），命中顺序 = 声明顺序。
- 全部规则都没命中时落到默认结局「剧终」。
- 一个条件都没有命中的情况要想清楚：给最坏结局一条 `when affection <= 0` 这类兜底规则。

### 7. 音效 / 演出标记（预留）

```text
@sfx radio_static      ← 音效名（渲染为 ♪ 提示行，同时记入历史）
@bgm rainy_afternoon   ← 背景乐名（♫）
@anim signal_wave      ← 演出名（✦）
```

现阶段只做展示与留痕，Roadmap 里计划接入真实音频 / ASCII 演出。

### 8. 转义规则

反斜杠 `\` 在剧本里是转义符，任何地方都生效：

| 写法 | 含义 |
|------|------|
| `\:` | 字面冒号 `:`（台词分隔符后面用） |
| `\\` | 字面反斜杠 `\` |
| `\n` | 换行 |
| `\t` | 制表符 |
| `\其他` | 就是那个字符本身（如 `\q` → `q`） |

行尾出现孤立的 `\`、引号未闭合、未知指令、标签重复、跳转目标不存在……都会**带行号报错**，例如：

```text
story/xx.vn:14: 跳转目标标签 'c9' 不存在
```

### 9. 一个能直接跑的最小剧本

把下面内容存成 `story/my.vn`，然后 `python demo.py --script story/my.vn`：

```text
# 我的第一个剧本
@ending 勇气可嘉 when courage >= 1
@ending 平安是福 when courage == 0

@scene 天台
|天台上只有风。
澪: ……你来啦。
@choice
- 说出心意 -> brave
- 挥挥手离开 -> normal

@label brave
@set courage += 1
我: 嗯，我来啦。
@end

@label normal
澪: 那么，明天见。
@end
```

---

## 引擎架构

```text
                    ┌────────────────────────────────┐
                    │        story/*.vn             │  剧本 = 纯文本 DSL
                    └───────────────┬────────────────┘
                                    │ Script.from_file()
                    ┌───────────────▼────────────────┐
                    │   vn/script.py  解析器         │  行 → 结构化 Line 对象
                    │   文法校验 · 标签表 · 行号      │  错误行 → ScriptError(带行号)
                    └───────────────┬────────────────┘
                                    │ Script(lines, labels, endings)
            ┌───────────────────────▼───────────────────────────┐
            │        vn/engine.py  主循环  Engine.run()         │
            │   while state.line_index < len(lines): _step()    │
            │     Dialogue / Narration → 打字机 → 等待指令      │
            │     Choice   → 条件过滤可见项 → 菜单 → 跳转       │
            │     SetVar / If / Jump / Scene / Fx → 改状态流转  │
            │     End      → 结局判定（@ending 阈值规则）        │
            └──────────┬────────────────────────┬───────────────┘
                       │ 读写变量/节点/历史       │ 绘制事件
        ┌──────────────▼─────────────┐   ┌───────▼──────────────────┐
        │  vn/state.py  运行时状态    │   │  vn/render.py  终端渲染   │
        │  · 变量表（好感度 = 变量）   │   │  · 场景框 / 名牌 / 选项   │
        │  · 当前节点 line_index      │   │  · 打字机 cps / 按键跳过   │
        │  · 历史回看（上限 500 条）   │   │  · ANSI 配色 / NO_COLOR   │
        │  · JSON 多槽位存档读档       │   │  · KeyPoller（Win/POSIX） │
        └─────────────────────────────┘   └──────────────────────────┘

        demo.py —— 自动演示（autoplay 免回车 + 永远第 1 项）/ --play 交互入口
        管道输入到头（EOF）时交互模式自动转为静默继续，不会卡死
```

依赖关系只有一层：`engine` 用 `script` 与 `state`，用 `render` 画；`state` 用 `script` 的条件结构做求值。任何模块都可以单独拿去复用。

---

## 自带剧本：《雨季信号》

转学生澪总抱着哥哥留下的旧收音机，在放学后的教室里等一场「不存在的电台」。你要不要走过去，把纸巾递给她？

- 篇幅：约 5–8 分钟通关，5 个场景，全部读完约 4000 字
- 变量：`affection`（好感度）、`knows_truth`（真相线标记）、`courage`（勇气）
- 4 处分支点、2 处条件选项、4 个结局（阈值规则判定）

几条路线（数字为该分支的选择序号）：

- **1 → 1 → 1 → 1**（自动路线）：递纸巾、追问真相、陪她上天台、说出「一起去看海吗」——好感 6 + 真相，达成真结局 **「一起去看海」**
- **1 → 2 → 2 → 1**：递纸巾、请喝热可可、把票还她——好感 6 但没走真相线，**「天台上的约定」**
- **1 → 1 → 3 → 2**：递纸巾、追问、说出自己的心事、把话咽回去——好感 4，**「普通的放学路」**
- **2 → 3 → 3 → 2**：装没看见、转身离开、沉默到底——好感 -2，**「擦肩而过」**

试试只改一个选择，看结局横幅怎么变。

---

## 项目结构

```text
visual-novel/
├── demo.py              # 自动演示 / --play 交互入口
├── vn/
│   ├── script.py        # 剧本 DSL 解析器（文法校验、标签、结局规则）
│   ├── state.py         # 变量、好感度、历史、JSON 多槽位存档
│   ├── engine.py        # 主循环、选项菜单、命令、结局判定
│   └── render.py        # 场景框、名牌、打字机、ANSI、KeyPoller
├── story/
│   └── rain_signal.vn   # 自带完整 demo 剧本《雨季信号》
├── tests/               # 114 个单元测试（unittest，零依赖）
├── output/              # playthrough.txt 与 saves/ 产物（运行时生成）
├── README.md
├── LICENSE              # MIT
└── .gitignore
```

---

## English Summary

**vn** is a dependency-free terminal visual-novel / text-adventure engine written in pure Python 3.10+ standard library. The engine (`vn/` package, 4 small modules) is fully decoupled from content: stories are plain-text DSL files (`story/*.vn`) anyone can write in a text editor.

Features: typewriter dialogue with adjustable speed and key-to-skip, speaker name-plates, scene title boxes, numbered choice menus with per-option conditions, variable/affection-based conditional jumps (`@if affection >= 5 and flag == 1 -> label`), multi-ending threshold rules, JSON multi-slot save/load, scroll-back history, and ANSI colors with automatic `NO_COLOR`/non-TTY fallback.

Bundled playable demo "Rain Signal" (《雨季信号》) ships with 4 branch points and 4 endings; `python demo.py` auto-runs one full route to the true ending and writes the transcript to `output/playthrough.txt`, while `python demo.py --play` starts an interactive session. Test suite: `python -m unittest discover -s tests` (114 tests).

---

## Roadmap

- **图片背景**：`@scene` 支持 ANSI 全彩/半格字符背景画，或外部图片经协议转发到终端查看器
- **存档 UI**：可视槽位菜单（缩略时间/场景/好感度），替代现在的 `s N` / `l N` 数字命令；自动存档点
- **更多剧本模板**：校园、悬疑、恋爱回合作成「模板包」，新作者复制改字即可开写
- **演出落地**：`@sfx` / `@bgm` 接入系统提示音或外部播放器；`@anim` 做 ANSI 抖动/闪烁演出
- **历史跳转**：回看列表支持跳回任意历史点（撤销式时间线）
- **JSON 后端**：除 DSL 外支持 `story.json` 双格式输入，方便编辑器生成剧本

---

## 许可

MIT，详见 [LICENSE](LICENSE)。写自己的故事吧。
