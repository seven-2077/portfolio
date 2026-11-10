"""统一的异常层次。

设计原因：MiniDB 把所有「可预期错误」（语法、约束、类型、存储损坏）
都收敛到 :class:`MiniDBError` 一个基类之下，REPL 与测试只需要
``except MiniDBError`` 就能一网打尽；而测试专用的 :class:`SimulatedCrash`
故意**不**继承它 —— 崩溃是异常控制流，必须穿透语句级的回滚清理，
否则模拟崩溃就变成了「干净的回滚」，恢复逻辑永远测不到。
"""

from __future__ import annotations


class MiniDBError(Exception):
    """MiniDB 所有可预期错误的基类。"""


class SQLSyntaxError(MiniDBError):
    """词法/语法错误，携带行列位置便于 REPL 定位。"""

    def __init__(self, message: str, line: int = 0, col: int = 0) -> None:
        self.line = line
        self.col = col
        position = f" (line {line}, column {col})" if line else ""
        super().__init__(f"{message}{position}")


class UnterminatedStringError(SQLSyntaxError):
    """字符串字面量没闭合 —— REPL 靠它判断「还要继续读一行」。"""


class SchemaError(MiniDBError):
    """表/列/索引不存在，或名称冲突。"""


class TypeMismatchError(MiniDBError):
    """值的类型与列类型不匹配，或两种类型之间不可比较。"""


class ConstraintError(MiniDBError):
    """违反约束（主键重复、NOT NULL、UNIQUE）。"""


class DuplicateKeyError(ConstraintError):
    """主键或唯一索引冲突。"""


class NotNullError(ConstraintError):
    """NOT NULL 列收到了 NULL。"""


class StorageError(MiniDBError):
    """页损坏、行过大、文件格式不合法等底层存储问题。"""


class DatabaseClosedError(MiniDBError):
    """数据库句柄已因崩溃模拟或 close() 而失效。"""


class SimulatedCrash(Exception):
    """测试专用：模拟进程在某个提交阶段被 kill。

    只在 ``Database.set_failpoint()`` 触发时抛出。它继承自 Exception
    而非 MiniDBError，以便绕过语句失败时的清理逻辑（清理会把 WAL 抹掉，
    那样就测不到恢复了）。
    """
