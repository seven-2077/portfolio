"""MiniDB —— 用 408 的知识从零写成的教学型嵌入式 SQL 数据库。

纯 Python 标准库实现：4KB 页式堆存储、B+ 树索引、手写递归下降
SQL 解析器、Volcano 迭代器执行器、WAL + redo 崩溃恢复。

快速上手::

    from minidb import connect
    db = connect("demo.db")
    db.execute("CREATE TABLE t (id INT PRIMARY KEY, name TEXT);")
    db.execute("INSERT INTO t VALUES (1, 'hello');")
    print(db.query("SELECT * FROM t;"))

命令行 REPL：``python -m minidb [数据库文件]``
"""

from .database import FAILPOINTS, Database, Result, connect
from .errors import (
    ConstraintError,
    DatabaseClosedError,
    DuplicateKeyError,
    MiniDBError,
    NotNullError,
    SQLSyntaxError,
    SchemaError,
    SimulatedCrash,
    StorageError,
    TypeMismatchError,
    UnterminatedStringError,
)
from .parser import parse_one, parse_script

__version__ = "0.1.0"

__all__ = [
    "Database", "Result", "connect", "FAILPOINTS", "__version__",
    "parse_one", "parse_script",
    "MiniDBError", "SQLSyntaxError", "UnterminatedStringError",
    "SchemaError", "TypeMismatchError",
    "ConstraintError", "DuplicateKeyError", "NotNullError",
    "StorageError", "DatabaseClosedError", "SimulatedCrash",
]
