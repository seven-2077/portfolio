# study-timer · 考研学习计时与目标进度

给「每天 4-8h」这个目标做的最小可用记录器：开一段、停一段、看进度条。纯 Python 标准库，零依赖，`python study_timer.py` 直接跑。

---

## 快速上手

```powershell
# 开始一段学习（科目 + 可选备注）
python study_timer.py start 408 数据结构第三章

# 结束并入库（自动算时长、刷新今日进度条）
python study_timer.py stop

# 手动补录一段（今天忘了开计时的时候）
python study_timer.py add -m 90 -s math "高数极限专项"

# 查看
python study_timer.py today    # 今日明细 + 科目分布 + 4h 目标进度条
python study_timer.py week     # 本周逐日热力条

# 番茄钟：学 25 休 5，每完成一个自动入库（参数可改）
python study_timer.py pomodoro 50 10
```

---

## 它和别的计时器不一样的两处

**进度条按你的目标区间设计**：4 小时算达标（满格），冲到 8 小时会标出「已达 8h 上限区」。不是通用的番茄土豆，就是照着你的备考节奏长的。

**科目分布直接暴露偏科**：`today` 末尾按科目聚合时长，408 学了多少、英语落了多少，一眼看到 —— 比「今天学了 5 小时」这种总数诚实得多。

---

## 数据存哪

`data/log.json`（全部记录）与 `data/state.json`（进行中的那一段）。都是普通 JSON，随时可删可备份；想导 CSV 十行代码的事，需要时喊 AI 写。

注意：`start`/`stop` 靠 state 文件配对，同一时刻只支持一段计时（番茄钟会自己逐段入库）。

---

## 测试

```powershell
python -m unittest discover -s tests -v
```

14 个用例覆盖：时长计算与非法输入、按日/周聚合（周一起算）、科目分布排序、进度条各档位、CLI 全链路（临时数据目录，不污染真实记录）。
