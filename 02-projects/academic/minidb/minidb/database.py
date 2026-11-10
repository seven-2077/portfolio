"""数据库门面：连接、事务、WAL 提交协议、DDL 执行与崩溃恢复。

打开顺序为什么是「先恢复、后开 Pager」？
    :func:`~minidb.wal.recover_database` 直接对数据库文件做 redo，
    此时不能有任何页缓存存在 —— 否则缓存里会留着恢复前的旧页，
    后续读到的就是过期数据。所以恢复永远发生在 Pager 构造之前。

事务提交协议（与 wal.py 文档的 ①②③④ 一致）::

    1. 若 catalog 有变更，先 catalog.save() —— 元数据页与数据页
       必须在同一次提交里落盘，否则会「表头说有 3 页、实际只有 2 页」
    2. 取全部脏页映像，逐页追加进 WAL（PAGE 记录）
    3. 追加 COMMIT 记录，fsync(WAL)          ← 持久化点，跨过才算数
    4. 分两批写回数据页并 fsync（中间可注入「写了一半」的崩溃）
    5. 截断 WAL（checkpoint：数据库文件本身就是持久检查点）

为什么提交时才写页映像，而不是修改时就写？
    单进程、单语句事务、no-steal（脏页从不提前落盘）的前提下，
    事务开始时 WAL 必为空，提交时写入的「脏页终态」就是恢复需要的
    全部信息 —— 日志量减半，恢复仍是纯 redo、天然幂等。
    修改时写日志（真正的 physiological logging）是并发控制进场后
    才需要的复杂度，Roadmap 里的 MVCC 会把它请回来。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .ast import (
    CreateIndex,
    CreateTable,
    Delete,
    Explain,
    Insert,
    Select,
    Statement,
    Update,
)
from .btree import BPlusTree
from .catalog import Catalog, Column, IndexInfo, TableInfo
from .errors import (
    DatabaseClosedError,
    DuplicateKeyError,
    MiniDBError,
    SchemaError,
    SimulatedCrash,
    SQLSyntaxError,
)
from .executor import Executor
from .pager import Pager
from .parser import parse_one, parse_script
from .planner import Planner
from .table import Index, Table, resolve_columns
from .wal import Wal, recover_database

#: 崩溃故障点：提交前 / 提交后回写前 / 回写中途 / 截断 WAL 前
FAILPOINTS = ("before_commit", "after_commit", "mid_writes", "before_truncate")


class Result:
    """一条语句的结果（REPL 与测试都靠它）。"""

    def __init__(self, kind: str, columns: list[str] | None = None,
                 rows: list[tuple] | None = None, rowcount: int = 0,
                 message: str = "", plan_text: str | None = None):
        self.kind = kind                # select / insert / update / delete / ddl / explain
        self.columns = columns or []
        self.rows = rows or []
        self.rowcount = rowcount
        self.message = message
        self.plan_text = plan_text       # EXPLAIN 时的计划树

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Result {self.kind} rows={len(self.rows)} rowcount={self.rowcount}>"


class Database:
    """一个单进程、单连接的嵌入式数据库。

    Args:
        path: 数据库文件路径（目录会自动创建）。
            页大小是编译期常量 4096（见 ``pager.PAGE_SIZE``），
            教学库里把它做成参数没有收益，改动点反而多一处。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wal_path = self.path.with_name(self.path.name + ".wal")

        # 1) 先恢复：redo 直接写文件，此时还没有任何页缓存
        self._recover(wal_path)

        # 2) 再开页管理与元数据
        self.pager = Pager(self.path)
        self.catalog = Catalog(self.pager)
        self.catalog.load()             # catalog_start=0 时空库，load 是 no-op

        # 3) 最后拿 WAL 句柄（w+b 会截断 —— 恢复后的日志已无使命）
        self.wal = Wal(wal_path)
        self._failpoints: set[str] = set()
        self._closed = False
        # planner 持有 catalog/pager 的引用，两者都是长生命周期对象，
        # 可以安全复用（planner 自身无状态）
        self._planner = Planner(self.catalog, self.pager)

    # ------------------------------------------------------------------
    # 打开 / 关闭
    # ------------------------------------------------------------------
    def _recover(self, wal_path: Path) -> None:
        """启动即恢复：扫 WAL，把最后一次 COMMIT 之前的页映像 redo 回文件。"""
        replayed = recover_database(self.path, wal_path)
        if replayed:
            print(f"[minidb] 崩溃恢复：重放 {replayed} 页（纯 redo，幂等）")

    def close(self) -> None:
        """关闭：未提交的事务按提交处理（教学简化），然后释放句柄。"""
        if self._closed:
            return
        try:
            if not self.pager.closed:
                self.commit()
        finally:
            self.pager.close()
            self.wal.close()
            self._closed = True

    def kill(self) -> None:
        """模拟进程被杀：直接关闭句柄，不提交、不清缓冲。

        这是崩溃恢复测试的前置动作 —— 与真实进程收到 SIGKILL 时
        「用户态内存全部蒸发、磁盘上留下半截状态」一致。
        """
        self._closed = True
        self.pager.close()
        self.wal.close()

    def _check_open(self) -> None:
        if self._closed:
            raise DatabaseClosedError(f"数据库已关闭: {self.path}")

    # ------------------------------------------------------------------
    # 事务
    # ------------------------------------------------------------------
    @contextmanager
    def transaction(self):
        """with 事务块：异常回滚（丢日志 + 丢缓冲），正常退出提交。"""
        self.begin()
        try:
            yield
        except BaseException:
            self.rollback()
            raise
        else:
            self.commit()

    def begin(self) -> None:
        """开始事务：清空 WAL。

        正常路径上它已经是空的（上一事务在 commit 里截断过）；
        不为空只可能是上一事务中途失败还没回滚 —— 那些日志本来就该丢。
        """
        self.wal.reset()

    def commit(self) -> None:
        """提交：先日志后数据（WAL 的全部意义所在）。

        崩溃故障点插在协议步骤之间，模拟「进程在任意时刻被 kill」。
        """
        self._check_open()
        if self._fail("before_commit"):
            raise SimulatedCrash("before_commit")

        if self.catalog.dirty:
            self.catalog.save()     # 元数据页进脏页集，与数据页同一次提交

        images = self.pager.dirty_images()
        if not images:
            self.wal.reset()        # 无脏页（纯读/空事务）：日志直接归零
            return

        # ① 页映像先进日志
        for pid, img in images.items():
            self.wal.append_page(pid, img)
        # ② COMMIT + fsync —— 持久化点
        self.wal.append_commit()
        self.wal.sync()

        if self._fail("after_commit"):
            raise SimulatedCrash("after_commit")

        # ③ 分两批写回，中间可注入「回写了一半」的崩溃
        items = sorted(images.items())
        mid = len(items) // 2
        self.pager.write_images(dict(items[:mid]))
        if self._fail("mid_writes"):
            raise SimulatedCrash("mid_writes")
        self.pager.write_images(dict(items[mid:]))
        self.pager.clear_dirty()

        if self._fail("before_truncate"):
            raise SimulatedCrash("before_truncate")

        # ④ checkpoint：数据库文件已是持久状态，日志退役
        self.wal.reset()

    def rollback(self) -> None:
        """回滚：丢日志、丢内存缓冲 —— 修改从未落盘，什么都不用恢复。"""
        self.wal.reset()
        self.pager.discard_buffers()
        self.pager.reload_header()  # 分配指针（next_page/freelist）拨回磁盘真相
        self.catalog.load()         # 元数据同样拨回磁盘真相

    # ------------------------------------------------------------------
    # 故障注入（测试与演示用）
    # ------------------------------------------------------------------
    def inject_failpoint(self, name: str) -> None:
        """设置崩溃故障点，命中一次后自动解除，抛 :class:`SimulatedCrash`。

        Args:
            name: ``FAILPOINTS`` 中之一
        """
        if name not in FAILPOINTS:
            raise MiniDBError(f"未知故障点 {name}，可选：{', '.join(FAILPOINTS)}")
        self._failpoints.add(name)

    #: 兼容别名（errors.py 文档里用的是这个名字）
    set_failpoint = inject_failpoint

    def clear_failpoints(self) -> None:
        self._failpoints.clear()

    def _fail(self, name: str) -> bool:
        if name in self._failpoints:
            self._failpoints.discard(name)     # 一次性
            return True
        return False

    # ------------------------------------------------------------------
    # 语句执行
    # ------------------------------------------------------------------
    def execute(self, sql: str) -> Result:
        """执行单条 SQL，返回结果。

        单条语句本身即一个事务（教学简化；``transaction()`` 可组合多条）。
        """
        self._check_open()
        stmt = parse_one(sql)       # 语法错误发生在 begin 之前，不留任何痕迹
        return self._run(stmt)

    def _run(self, stmt: Statement) -> Result:
        """把一条已解析语句跑成事务：begin -> 执行 -> commit/rollback。"""
        self.begin()
        try:
            result = self._dispatch(stmt)
        except BaseException:
            self.rollback()
            raise
        self.commit()
        return result

    def _dispatch(self, stmt: Statement) -> Result:
        if isinstance(stmt, CreateTable):
            return self._create_table(stmt)
        if isinstance(stmt, CreateIndex):
            return self._create_index(stmt)
        if isinstance(stmt, Explain):
            return self._explain(stmt.stmt)
        if isinstance(stmt, (Select, Insert, Update, Delete)):
            plan, names = self._planner.build(stmt)
            rows, count = Executor.run(plan)
            if isinstance(stmt, Select):
                return Result("select", columns=names, rows=rows, rowcount=count)
            kind, verb = {
                Insert: ("insert", "插入"),
                Update: ("update", "更新"),
                Delete: ("delete", "删除"),
            }[type(stmt)]
            return Result(kind, rowcount=count, message=f"{verb} {count} 行")
        raise SQLSyntaxError(f"不支持的语句: {type(stmt).__name__}")

    # --- DDL -----------------------------------------------------------
    def _create_table(self, stmt: CreateTable) -> Result:
        if self.catalog.find_table(stmt.name) is not None:
            raise SchemaError(f"表已存在: {stmt.name}")

        columns = [
            Column(c.name, c.col_type, c.primary_key, c.not_null)
            for c in stmt.columns
        ]
        info = TableInfo(name=stmt.name, columns=columns, first_page=0, last_page=0)

        pk = [c for c in columns if c.primary_key]
        if pk:
            # 主键索引随表自动创建：唯一 + 主键标记（.schema 不重复展示）。
            # 根页当场分配，与表头同一次提交落盘。
            root = BPlusTree.create(self.pager).root_page
            info.indexes.append(IndexInfo(
                name=f"{stmt.name.lower()}_pk",
                table=stmt.name,
                columns=[c.name for c in pk],
                root_page=root,
                unique=True,
                primary=True,
            ))

        self.catalog.add_table(info)    # 重复表名在此抛 SchemaError
        return Result("ddl", message=f"已创建表 {stmt.name}")

    def _create_index(self, stmt: CreateIndex) -> Result:
        info = self.catalog.require_table(stmt.table)
        if not self.catalog.index_name_available(stmt.name):
            raise SchemaError(f"索引名已存在: {stmt.name}")
        resolve_columns(info, stmt.columns)     # 列存在 + 不重名

        # 按表定义的大小写规范化列名（显示好看，查找仍大小写不敏感）
        norm = [info.columns[info.column_index(c)].name for c in stmt.columns]
        root = BPlusTree.create(self.pager).root_page
        idx_info = IndexInfo(
            name=stmt.name, table=info.name, columns=norm,
            root_page=root, unique=stmt.unique, primary=False,
        )
        info.indexes.append(idx_info)
        self.catalog.touch()

        # 回填：把现有行灌进新树。UNIQUE 索引遇到重复值当场拒绝 ——
        # 整个语句随后回滚（含刚分配的根页），不会留下半截索引。
        table = Table(self.pager, info, self.catalog)
        idx = Index(self.pager, idx_info, info, self.catalog)
        for rowid, row in table.scan():
            if stmt.unique and not any(row[p] is None for p in idx.positions):
                by_col = {n.lower(): row[p] for n, p in zip(norm, idx.positions)}
                prefix = idx.prefix_for(by_col)
                if prefix is not None and idx.key_exists(prefix):
                    cols = ", ".join(norm)
                    raise DuplicateKeyError(
                        f"创建 UNIQUE 索引失败：{cols} 存在重复值"
                    )
            idx.insert_entry(row, rowid)

        return Result("ddl", message=f"已创建索引 {stmt.name}")

    def _explain(self, stmt: Statement) -> Result:
        lines = self._planner.explain(stmt)     # 含 DDL 分支与 Explain 剥壳
        text = "\n".join(lines)
        return Result("explain", plan_text=text, message=text)

    # ------------------------------------------------------------------
    # 表访问
    # ------------------------------------------------------------------
    def table(self, name: str) -> Table:
        """按名取表（大小写不敏感）。每次新建实例 —— 与 planner 同策略，
        避免跨语句持有过期的元数据引用。"""
        self._check_open()
        return Table(self.pager, self.catalog.require_table(name), self.catalog)

    def schema(self, table: str | None = None) -> list[str]:
        """建表语句列表（供 REPL 的 .schema 使用）。不带表名则全部。"""
        if table is not None:
            return self.catalog.ddl_for(table)
        return self.catalog.all_ddl()

    def catalog_names(self) -> tuple[list[str], list[str]]:
        """返回 (表名, 非主键索引名)，供 REPL 元命令使用。"""
        tables = list(self.catalog.tables)
        indexes = [
            i.name
            for t in self.catalog.tables.values()
            for i in t.indexes
            if not i.primary
        ]
        return tables, indexes

    # ------------------------------------------------------------------
    # 高层 API（Python 嵌入接口，测试与 demo 也用它）
    # ------------------------------------------------------------------
    def query(self, sql: str, *args: Any) -> list[tuple]:
        """便捷查询：执行 SELECT 并返回行列表。

        ``?`` 占位符按位置绑定（在词法层替换为字面量，教学实现，
        真实数据库会在解析后绑定）。
        """
        if args:
            sql = _bind(sql, args)
        result = self.execute(sql)
        return result.rows

    def executescript(self, script: str) -> list[Result]:
        """执行多条语句（分号分隔），每条独立成事务，返回全部结果。"""
        self._check_open()
        return [self._run(stmt) for stmt in parse_script(script)]


def _bind(sql: str, args: tuple) -> str:
    """把 ``?`` 占位符替换成字面量（值经 SQL 字面量转义）。"""
    parts = sql.split("?")
    if len(parts) - 1 != len(args):
        raise SQLSyntaxError(
            f"参数个数不匹配：需要 {len(parts) - 1} 个，收到 {len(args)} 个"
        )
    out = parts[0]
    for piece, value in zip(parts[1:], args):
        out += _literal(value) + piece
    return out


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise SQLSyntaxError(f"不支持的绑定类型：{type(value).__name__}")


def connect(path: str | Path, **kw: Any) -> Database:
    """打开（或创建）数据库 —— 最常用的入口。"""
    return Database(path, **kw)


__all__ = [
    "Database", "Result", "connect", "FAILPOINTS",
    "MiniDBError", "SimulatedCrash", "DuplicateKeyError", "SchemaError",
    "DatabaseClosedError",
]
