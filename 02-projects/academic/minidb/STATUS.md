# minidb · 交付状态（2026-11-05 上午）

状态：**已交付 · 93 测试全绿**。断点恢复施工完成，全部任务书交付标准已达成。

## 施工记录（resume 后）

1. `database.py` 整体重写，对接真实接口（Planner/Executor/Catalog/Wal/Pager）
   + 四步 WAL 提交协议 + 崩溃故障点（before_commit / after_commit /
   mid_writes / before_truncate）
2. REPL（`minidb/repl.py` + `__main__.py`）：分号缓冲多语句、
   `.tables/.schema/.indexes/.help/.quit/.crash` 元命令、对齐表格渲染、
   stdin/stdout 可注入（测试用 StringIO 驱动）
3. 测试套件 `tests/`：**93 个用例、7 文件、约 900 行，一键全绿**
   （含 4 个故障点崩溃恢复、B+ 树、解析、执行、REPL 覆盖）
4. `README.md`（quickstart 3 命令、mermaid+ASCII 架构图、设计取舍、
   408 对应、Roadmap、English summary）+ `LICENSE`(MIT) + `.gitignore`
   + `demo.py` 端到端演示（含崩溃恢复实录）
5. 删除孤儿文件 `expr.py`（功能早已由 `ast.eval_expr` 承担，无任何引用）

## 联调期发现并修复的 7 个 bug（全部有测试对应）

1. `pager.py`：头页 setter 只标脏不重新打包 page 0 字节 →
   WAL 里存的是旧头，重开后 catalog_start/空闲链表全丢
2. `btree.py create`：切片赋值把 4096 页截成 12 字节 → WAL 完整性校验报错
3. `operators.py`：`COUNT(*)` 给 `_AggState.add` 传 None 被当 NULL 跳过 → 恒 0
4. `wal.py recover_database`：`committed` 二元组被按三元组解包 → 恢复崩溃
5. `btree.py range_scan`：上界判停写反（`key < end` 应为 `key > end`）→
   范围扫描恒空 / 等值扫描漏上界
6. `table.py Index.key_for`：主键索引把 enc(pk) 拼两遍，
   与 planner 单段边界键对不上 → 主键范围条件全部失准
7. `tokenizer.py`：`ON` 不在关键字表 → `CREATE INDEX ... ON ...` 语法错误

另有 codec 类型别名扩充（VARCHAR/DOUBLE/BIGINT/STRING）与
parser 支持 `VARCHAR(255)` 长度修饰（接受但不执行）。

## 交付物清单

- `minidb/` 18 个 py 文件（核心约 3800 行）
- `tests/` 7 个文件 93 用例（约 870 行）
- `README.md` · `LICENSE`(MIT) · `.gitignore` · `demo.py`
- 运行入口：`python -m unittest discover -s tests -v` /
  `python demo.py` / `python -m minidb`

## 主控验收清单

- [x] `python -m unittest discover -s tests -v` → 93 OK
- [x] `python demo.py` 端到端（建表→30行→聚合→崩溃→redo→重启）
- [ ] `git init` 提交（身份 seven）—— 主控处理，施工队未做任何 git 操作
- [ ] ROADMAP 状态行「minidb 施工中」→ 已验收 —— 主控处理
