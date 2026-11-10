"""值编码模块 —— MiniDB 里存在两类「字节化」，职责截然不同。

1. **行记录编码**（:func:`encode_row` / :func:`decode_row`）
   堆页里存的字节，按表的 schema 解释：NULL 位图 + 各字段顺序拼接。
   追求紧凑与自解释，不需要保序。

2. **索引键编码**（:func:`encode_key` / :func:`decode_key`）
   B+ 树里用来排序的字节，必须满足 **字节序 == 值序**：
   这样节点内部比较大小就退化成 ``memcmp``（C 语言里的 ``memcmp`` 正是
   408 里字符串比较的底层原语），树的查找路径上完全不用做类型分派。

保序编码的三个关键手法（面试/考试都可能问「为什么这样编码」）：

* **有符号整数**：把符号位翻转到最高位（``v ^ (1<<63)``），
  负数就落在无符号数的下半区，大端字节比较即得原序。
* **IEEE754 浮点**：正数翻符号位、负数按位取反 —— 经典的
  order-preserving float transform，使 ``bytes`` 比较 == 浮点比较。
* **变长文本**：UTF-8 字节后补 ``\\x00`` 终结符。终结符保证编码是
  **前缀自由** 的，于是 ``enc(a) + enc(b)`` 这种拼接仍保持字典序，
  二级索引的复合键 (列值, 主键) 才能直接 memcmp 排序。
  前提是文本里不能含 ``\\x00``，所以 INSERT 会拒绝含 NUL 的 TEXT。
"""

from __future__ import annotations

import struct
from typing import Sequence

from .errors import StorageError, TypeMismatchError

INT = "INT"
TEXT = "TEXT"
FLOAT = "FLOAT"
VALID_TYPES = (INT, TEXT, FLOAT)

# SQL 类型名 -> 内部规范名（教学库只支持三种类型，别名收一收）
_TYPE_ALIASES = {
    "INT": INT,
    "INTEGER": INT,
    "BIGINT": INT,
    "TEXT": TEXT,
    "VARCHAR": TEXT,
    "STRING": TEXT,
    "FLOAT": FLOAT,
    "DOUBLE": FLOAT,
    "REAL": FLOAT,
}

I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1

_TAG_NULL = 0x00  # 索引键：NULL 比任何非 NULL 都小（对齐 SQLite 的 NULL 最小语义）
_TAG_VAL = 0x01

_U64_MASK = (1 << 64) - 1


def normalize_type(token: str) -> str:
    """把 SQL 类型名规范化为内部类型名，未知类型抛 :class:`TypeMismatchError`。"""
    t = _TYPE_ALIASES.get(token.upper())
    if t is None:
        raise TypeMismatchError(f"不支持的列类型: {token}（支持 INT / TEXT / FLOAT）")
    return t


# ---------------------------------------------------------------------------
# 行记录编码
# ---------------------------------------------------------------------------

def _coerce(value, col_type: str, col_name: str):
    """把值校验/转换成列类型要求的 Python 类型。

    只做一处宽松转换：INT 字面量写入 FLOAT 列时提升为 float
    （``INSERT ... VALUES (1)`` 写进 FLOAT 列是合法且常见的）；
    其余一律严格 —— ``1.5`` 不会默默截断进 INT 列，教学库宁可报错。
    """
    if col_type == INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeMismatchError(f"列 {col_name} 是 INT，收到 {value!r}")
        if not I64_MIN <= value <= I64_MAX:
            raise StorageError(f"列 {col_name} 的值 {value} 超出 64 位整数范围")
        return value
    if col_type == FLOAT:
        if isinstance(value, bool):
            raise TypeMismatchError(f"列 {col_name} 是 FLOAT，收到 {value!r}")
        if isinstance(value, int):
            return float(value)
        if isinstance(value, float):
            return value
        raise TypeMismatchError(f"列 {col_name} 是 FLOAT，收到 {value!r}")
    # TEXT
    if not isinstance(value, str):
        raise TypeMismatchError(f"列 {col_name} 是 TEXT，收到 {value!r}")
    if "\x00" in value:
        # 索引键要求前缀自由（见模块 docstring），从入口统一拒绝最省事
        raise StorageError(f"列 {col_name} 的 TEXT 值不能包含 NUL 字符")
    return value


def encode_row(values: Sequence, columns: Sequence) -> bytes:
    """把一行值编码成堆页里的记录。

    布局：``[列数 u16][NULL 位图][字段依次拼接]``。
    位图让 NULL 不占字段空间；存列数是为了在解码时做一次健全性检查。
    """
    n = len(columns)
    bitmap = bytearray((n + 7) // 8)
    body = bytearray()
    for i, (value, col) in enumerate(zip(values, columns)):
        if value is None:
            bitmap[i >> 3] |= 1 << (i & 7)
            continue
        v = _coerce(value, col.col_type, col.name)
        if col.col_type == INT:
            body += struct.pack(">q", v)
        elif col.col_type == FLOAT:
            body += struct.pack(">d", v)
        else:
            raw = v.encode("utf-8")
            body += struct.pack(">I", len(raw)) + raw
    return struct.pack(">H", n) + bytes(bitmap) + bytes(body)


def decode_row(data: bytes, columns: Sequence) -> tuple:
    """把堆页记录解码回 Python 值元组，与 :func:`encode_row` 严格互逆。"""
    if len(data) < 2:
        raise StorageError("行记录损坏：长度不足")
    (n,) = struct.unpack_from(">H", data, 0)
    if n != len(columns):
        raise StorageError(f"行记录与表结构不匹配：记录 {n} 列，表 {len(columns)} 列")
    bitmap = data[2 : 2 + (n + 7) // 8]
    off = 2 + (n + 7) // 8
    out = []
    for i, col in enumerate(columns):
        if bitmap[i >> 3] & (1 << (i & 7)):
            out.append(None)
            continue
        if col.col_type == INT:
            (v,) = struct.unpack_from(">q", data, off)
            off += 8
        elif col.col_type == FLOAT:
            (v,) = struct.unpack_from(">d", data, off)
            off += 8
        else:
            (ln,) = struct.unpack_from(">I", data, off)
            off += 4
            if off + ln > len(data):
                raise StorageError("行记录损坏：TEXT 字段越界")
            v = data[off : off + ln].decode("utf-8")
            off += ln
        out.append(v)
    return tuple(out)


# ---------------------------------------------------------------------------
# 索引键的保序编码
# ---------------------------------------------------------------------------

def encode_key(value, col_type: str) -> bytes:
    """把一个值编码成**字节序 == 值序**的索引键（含 1 字节类型标签）。"""
    if value is None:
        return bytes([_TAG_NULL])
    if col_type == INT:
        v = _coerce(value, INT, "<key>")
        u = (v & _U64_MASK) ^ (1 << 63)  # 符号位翻转到最高位
        return bytes([_TAG_VAL]) + u.to_bytes(8, "big")
    if col_type == FLOAT:
        v = _coerce(value, FLOAT, "<key>")
        bits = struct.unpack(">Q", struct.pack(">d", v))[0]
        if bits & (1 << 63):  # 负数：按位取反，使「更大的负数」编码更小
            bits = bits ^ _U64_MASK
        else:  # 正数：翻转符号位，落入无符号数上半区
            bits = bits ^ (1 << 63)
        return bytes([_TAG_VAL]) + bits.to_bytes(8, "big")
    v = _coerce(value, TEXT, "<key>")
    return bytes([_TAG_VAL]) + v.encode("utf-8") + b"\x00"  # 终结符 => 前缀自由


def decode_key(data: bytes, col_type: str):
    """:func:`encode_key` 的逆运算。"""
    if data == bytes([_TAG_NULL]):
        return None
    if not data or data[0] != _TAG_VAL:
        raise StorageError("索引键损坏：缺少类型标签")
    body = data[1:]
    if col_type == INT:
        if len(body) != 8:
            raise StorageError("索引键损坏：INT 键长度错误")
        u = int.from_bytes(body, "big") ^ (1 << 63)
        return u - (1 << 64) if u >= (1 << 63) else u
    if col_type == FLOAT:
        if len(body) != 8:
            raise StorageError("索引键损坏：FLOAT 键长度错误")
        bits = int.from_bytes(body, "big")
        bits = bits ^ (1 << 63) if bits & (1 << 63) else bits ^ _U64_MASK
        return struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    if not body.endswith(b"\x00"):
        raise StorageError("索引键损坏：TEXT 键缺少终结符")
    return body[:-1].decode("utf-8")


def compare_values(a, b) -> int:
    """SQL 三值逻辑下的值比较：返回 -1/0/1；NULL 最小；跨类型报错。

    同时服务两处：表达式求值里的 ``< <= > >=``，以及 ORDER BY 的排序比较。
    把「NULL 排最前」和「类型不可比就报错」集中在一处，
    两处行为天然一致（这正是 SQLite 的比较语义）。
    """
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return -1 if a < b else (0 if a == b else 1)
    if isinstance(a, str) and isinstance(b, str):
        return -1 if a < b else (0 if a == b else 1)
    raise TypeMismatchError(f"类型不可比较: {type(a).__name__} 与 {type(b).__name__}")


# ---------------------------------------------------------------------------
# rowid（行标识）编解码：页号 << 16 | 槽号，正好塞进 8 字节
# ---------------------------------------------------------------------------

def encode_rowid(rowid: int) -> bytes:
    return struct.pack(">Q", rowid)


def decode_rowid(data: bytes) -> int:
    if len(data) != 8:
        raise StorageError("索引值损坏：rowid 应为 8 字节")
    return struct.unpack(">Q", data)[0]


def make_rowid(page_no: int, slot: int) -> int:
    return (page_no << 16) | slot


def split_rowid(rowid: int) -> tuple[int, int]:
    return rowid >> 16, rowid & 0xFFFF
