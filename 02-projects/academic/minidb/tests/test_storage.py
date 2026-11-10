"""存储层测试：行编解码、索引键保序、页分配/空闲链表、堆 CRUD。"""

from __future__ import annotations

from support import TempDbCase

from minidb.catalog import Column, TableInfo
from minidb.codec import (
    decode_key,
    decode_row,
    encode_key,
    encode_row,
    normalize_type,
)
from minidb.errors import TypeMismatchError
from minidb.heap import TableHeap
from minidb.pager import PAGE_SIZE, Pager

COLS = [
    Column("id", "INT"),
    Column("name", "TEXT"),
    Column("score", "FLOAT"),
    Column("note", "TEXT"),
]


class TestRowCodec(TempDbCase):
    """行序列化：NULL 位图、类型严格性、往返一致。"""

    def test_roundtrip_with_null(self) -> None:
        values = (42, "你好，世界", 3.14, None)
        blob = encode_row(values, COLS)
        self.assertEqual(decode_row(blob, COLS), values)

    def test_roundtrip_many_rows(self) -> None:
        for i in range(50):
            values = (i, f"name-{i}", i * 1.5, None if i % 2 else "x")
            self.assertEqual(decode_row(encode_row(values, COLS), COLS), values)

    def test_type_strictness(self) -> None:
        # 1.5 不允许默默截断进 INT 列 —— 教学库宁可报错
        with self.assertRaises(TypeMismatchError):
            encode_row((1.5, "a", 1.0, None), COLS)
        # 反向放宽：INT 字面量写入 FLOAT 列提升为 float
        row = encode_row((1, "a", 2, None), COLS)
        self.assertEqual(decode_row(row, COLS)[2], 2.0)

    def test_null_bitmap_saves_space(self) -> None:
        with_null = encode_row((1, None, None, None), COLS)
        without = encode_row((1, "a", 2.0, "b"), COLS)
        # NULL 不占字段空间：全 NULL 行应明显更短
        self.assertLess(len(with_null), len(without))

    def test_normalize_type(self) -> None:
        self.assertEqual(normalize_type("varchar"), "TEXT")
        self.assertEqual(normalize_type("int"), "INT")
        self.assertEqual(normalize_type("double"), "FLOAT")
        with self.assertRaises(TypeMismatchError):
            normalize_type("BLOB")


class TestKeyCodec(TempDbCase):
    """索引键的「字节序 == 值序」—— B+ 树能用 memcmp 排序的前提。"""

    def test_int_order(self) -> None:
        values = [-2 ** 63, -100, -1, 0, 1, 99, 2 ** 63 - 1]
        keys = [encode_key(v, "INT") for v in values]
        self.assertEqual(keys, sorted(keys))

    def test_float_order(self) -> None:
        values = [-1e300, -2.5, -0.0, 0.0, 2.5, 1e300]
        keys = [encode_key(v, "FLOAT") for v in values]
        self.assertEqual(keys, sorted(keys))

    def test_text_prefix_free(self) -> None:
        # 前缀自由：ab 的编码必须落在 abc 之前，终结符保证不错乱
        self.assertLess(encode_key("ab", "TEXT"), encode_key("abc", "TEXT"))

    def test_null_sorts_first(self) -> None:
        self.assertLess(encode_key(None, "INT"), encode_key(-2 ** 63, "INT"))

    def test_key_roundtrip(self) -> None:
        for value, t in [(7, "INT"), (-7, "INT"), (2.5, "FLOAT"),
                         ("hello", "TEXT"), (None, "TEXT")]:
            self.assertEqual(decode_key(encode_key(value, t), t), value)


class TestPager(TempDbCase):
    """页分配、空闲链表复用、头页持久化。"""

    def test_allocate_incremental(self) -> None:
        pager = Pager(self.tmp / "p.db")
        a, b = pager.allocate(), pager.allocate()
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(pager.next_page_no, 3)  # page 0 占位
        pager.close()

    def test_freelist_lifo_and_zeroing(self) -> None:
        pager = Pager(self.tmp / "p.db")
        a, b = pager.allocate(), pager.allocate()
        # 往 a 写点「上一任住户」的数据
        pager.buffer(a)[:] = b"\xff" * PAGE_SIZE
        pager.free(a)
        self.assertEqual(pager.freelist_head, a)
        c = pager.allocate()          # LIFO：复用的正是 a
        self.assertEqual(c, a)
        # 复用页必须整体清零，防数据泄漏给新主人
        self.assertEqual(bytes(pager.read(c)), bytes(PAGE_SIZE))
        self.assertNotEqual(pager.freelist_head, a)
        pager.close()

    def test_header_persists_across_reopen(self) -> None:
        path = self.tmp / "p.db"
        pager = Pager(path)
        pager.allocate()
        pager.allocate()
        pager.write_images(pager.dirty_images())   # 模拟提交落盘
        next_page = pager.next_page_no
        pager.close()

        again = Pager(path)
        self.assertEqual(again.next_page_no, next_page)
        again.close()


class TestHeap(TempDbCase):
    """堆：跨页插入、扫描、更新、删除。"""

    def _heap(self) -> tuple[TableHeap, TableInfo]:
        info = TableInfo(name="t", columns=COLS, first_page=0, last_page=0)
        return TableHeap(self.db.pager, info, lambda: None), info

    def test_insert_scan_get(self) -> None:
        heap, _ = self._heap()
        for i in range(200):    # 200 行 × ~60B 必然跨多个 4KB 页
            heap.insert((i, f"user-{i}", i * 0.5, None))
        rows = list(heap.scan())
        self.assertEqual(len(rows), 200)
        self.assertEqual([v[0] for _rid, v in rows], list(range(200)))
        first_rid = rows[0][0]
        self.assertEqual(heap.get(first_rid), (0, "user-0", 0.0, None))

    def test_update_moves_row(self) -> None:
        heap, _ = self._heap()
        rid = heap.insert((1, "old", 1.0, None))
        new_rid = heap.update(rid, (1, "new", 2.0, None))
        self.assertEqual(heap.get(new_rid), (1, "new", 2.0, None))
        # 槽位能原地复用时新旧 rowid 相同；换了位置则旧 rowid 必须失效
        if new_rid != rid:
            self.assertIsNone(heap.get(rid))
        # 无论哪种方式，扫描只能看到一行（不能出现新旧两份副本）
        self.assertEqual(len(list(heap.scan())), 1)

    def test_delete_tombstone(self) -> None:
        heap, _ = self._heap()
        rids = [heap.insert((i, f"n{i}", float(i), None)) for i in range(10)]
        heap.delete(rids[3])
        self.assertIsNone(heap.get(rids[3]))
        remaining = [v[0] for _r, v in heap.scan()]
        self.assertEqual(remaining, [0, 1, 2, 4, 5, 6, 7, 8, 9])
        # 墓碑腾出的空间还能被后续插入复用
        heap.insert((99, "re", 0.0, None))
        self.assertEqual(len(list(heap.scan())), 10)


if __name__ == "__main__":      # pragma: no cover
    import unittest
    unittest.main()
