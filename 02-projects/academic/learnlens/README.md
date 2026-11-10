# 知识透镜 · LearnLens · 备考过程的数据科学研究

用数据科学方法研究一个真实考研人的备考过程：自产数据（计时 + 日报 + 自测）讲个案故事，公开数据集（EdNet / OULAD）验证方法，交付**论文 · 诊断工具 · 内容素材**三轨成果。

当前状态：**第一期「数据管道」已实现** —— schema → ingest → weekly → cli 四段打通，纯 Python 标准库零依赖，79 个测试全绿。完整设计见 [RESEARCH-PLAN.md](./RESEARCH-PLAN.md)，建议先读它。

---

## 快速启动

Python 3.10+，Windows 可跑，无任何第三方依赖。在项目根目录执行三条命令：

```bash
cd 02-projects/academic/learnlens

# 1. 30 秒录一条自测：自动盖今天日期，落盘 learnlens/data/selftest.json
python -m learnlens log-test 408 数据结构第六章 85%

# 2. 解析日报（文件或目录）：三件事执行率、自测清单、当日时长
python -m learnlens report examples/reports --data-dir examples

# 3. 本周汇总表（周一起算）：每日时长、执行率、自测次数、平均正确率
python -m learnlens week --data-dir examples
```

跑测试：

```bash
python -m unittest discover -s tests -v    # 79 个用例，一键全绿
```

正确率三种写法都收：`85%`、`85`、`0.85`。

---

## 数据流

```text
 04-tools/study-timer/data/log.json        每日学习日报 .md           log-test 手动录入
 （start/end/minutes/subject/note）      （母版：05-ai/prompts/）    （30 秒一条）
            │                                    │                         │
            ▼                                    ▼                         ▼
     load_sessions()                      parse_report()             selftest.json
     按日/科目聚合                         checkbox 解析             （0–100 正确率）
     文件缺=空，损坏=报错            - [x] done / - [-] partial           │
            │                          - [ ] missed（或 # status:）        │
            │                          自测行「科目 | 章节 | 正确率」       │
            │                          失败 → 带行号的清晰错误             │
            └──────────────┬─────────────┴────────────────────────────────┘
                           ▼
                    ingest_all(data_dir)
                    按日对齐 → DayRecord { sessions + report + self_tests }
                    跨源精确去重：同一次自测不计两遍
                           │
              ┌────────────┴──────────────┐
              ▼                           ▼
        weekly.build_week()          report 子命令
        周一起算 · 7 天占位行          单日结构化摘要
        执行率 = done / 已回看              │
              │                           │
              ▼                           ▼
        week 子命令                 （下期：HTML 看板）
        终端表格 + 合计行
```

数据目录约定（`--data-dir` 指向的目录，缺哪路都行）：

```text
data_dir/
├── log.json        # study-timer 记录（不放这也会沿目录向上自动找 04-tools/study-timer/）
├── reports/*.md    # 每日学习日报（根目录 *.md 也收）
└── selftest.json   # log-test 手动录入的自测
```

---

## 口径约定

研究结论全靠这几条算术，写死在代码里并被测试钉住：

- **执行率 = done / 已回看数**（done + partial + missed）。`pending`（还没到回看时点的新计划）不进分母 —— 把「还没发生的事」算作未完成，会系统性低估执行率。
- **partial 严格不计入分子**，但单独显示计数，让「差一点就完成」不被一个百分比吃掉。
- **一周从周一开始**；周日复盘时「本周」含当天。
- **跨午夜学习段归开始那天**（「昨晚学到凌晨」算昨天的投入）。
- **正确率统一存 0–100 百分数**，小数写法在入口处转换，存储层永远单一口径。

---

## 与 RESEARCH-PLAN.md 的对应

本期（2026-11 第一期代码）实现了计划书的这些块：

- **第 2 节「数据资产与数据字典」** → `learnlens/schema.py`：`StudySession` / `DailyReport` / `SelfTest` 三类数据类，构造即校验 + JSON 序列化。
- **第 7 节下一步 1「日报母版加结构化字段」** → 母版（`05-ai/prompts/每日学习日报母版.md`）已带三件事与自测字段；`parse_report` 按其格式解析：`- [x]` / `- [-]` / `- [ ]` 三种标记、`# status:` 行内注释、`科目 | 章节 | 正确率` 自测行。
- **第 7 节下一步 2「learnlens 骨架 + ingest + 录入 CLI」** → 本期主体：`ingest.py`（摄入与按日对齐）、`cli.py`（`log-test` / `report` / `week` 三个子命令）、`weekly.py`（周聚合）。
- **第 3 节「ingest → clean → annotate → analyze → report 五段管道」** → 完成第一段 ingest 与 report 的终端雏形；clean / annotate / analyze 留给下期。
- **第 5 节里程碑 2026-11**「数据管道骨架与自测录入工具」✅ 达成。
- **RQ2 的数据基础**：三件事逐条 status（pending / done / partial / missed）已可直接产出执行率时间序列。
- **RQ3 的语料入口**：日报的 `free_text` 保留「今日成果 / 一句话点评」等非结构化原文，供后续 LLM 考点语义标注。

---

## 下一步

1. **EdNet 基线**（2026-12 窗口，计划书第 7 节第 3 件）：下载 EdNet 子集，跑通「行为序列 → 表现预测」的可复现 baseline 数字。
2. **分析模块** `learnlens/analyze.py`：RQ1 滞后互相关（当日时长 × 次日自测正确率）、RQ2 执行率序列的水平-趋势检验 —— 数据已按日对齐成 `DayRecord`，直接吃进来。
3. **真实数据接入**：study-timer 跑出 `log.json` 后，`week` 会自动沿目录向上找到它；把 Wiki inbox 的日报放进 `learnlens/data/reports/` 即完成三路合流。
4. **产品轨**：HTML 看板（时长 × 表现散点、执行率仪表）；**RQ3**：考点词表 + LLM 标注管线（8GB 显存量化 7B 方案见计划书第 3 节）。

---

## English summary

**LearnLens** is the data pipeline for an N-of-1 study of a real postgraduate-exam candidate's preparation process. Phase one implements the ingest layer of the research plan in pure Python 3.10+ standard library (zero dependencies):

- `learnlens/schema.py` — validated dataclasses (`StudySession`, `DailyReport`, `SelfTest`) with JSON round-trip serialization;
- `learnlens/ingest.py` — reads study-timer logs and parses daily-report Markdown (checkbox statuses, self-test lines) into day-aligned records, with line-numbered errors on malformed input;
- `learnlens/weekly.py` — week aggregation (Monday-based) with execution-rate and accuracy statistics;
- `learnlens/cli.py` — three low-friction commands: `log-test` (record a quiz result in 30 seconds), `report` (structured summary of a daily report), `week` (terminal table for the current week).

79 unit tests run green via `python -m unittest discover -s tests -v`. Next: EdNet baseline and the analysis module (lagged correlation, execution-rate time series).

---

## 项目结构

```text
learnlens/
├── RESEARCH-PLAN.md      研究计划书（先读它）
├── README.md             本文件
├── .gitignore            Python + data/
├── learnlens/            包本体（python -m learnlens 入口）
│   ├── schema.py         三类记录 + 校验 + JSON 序列化
│   ├── ingest.py         log.json / 日报 Markdown → 按日对齐
│   ├── weekly.py         周聚合（周一起算、执行率口径）
│   ├── cli.py            log-test / report / week 三命令
│   └── data/             自测数据落盘（git 忽略）
├── tests/                unittest 79 例（schema / ingest / weekly / cli）
└── examples/             样例数据：log.json + 3 份日报 + selftest.json
```
