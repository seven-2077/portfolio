"""B+ 树测试：插入/等值查找、范围扫描、分裂、叶子链、删除。"""

from __future__ import annotations

from support import TempDbCase

from minidb.btree import BPlusTree
from minidb.codec import encode_key


def k(i: int) -> bytes:
    return encode_key(i, "INT")


class TestBPlusTree(TempDbCase):
    def test_insert_and_search(self) -> None:
        tree = BPlusTree.create(self.db.pager)
        for i in range(500):
            tree.insert(k(i), f"v{i}".encode())
        for i in range(500):
            self.assertEqual(tree.search(k(i)), [f"v{i}".encode()])
        self.assertEqual(tree.search(k(9999)), [])
        self.assertEqual(tree.search(k(-1)), [])

    def test_full_range_scan_is_globally_sorted(self) -> None:
        # 乱序插入 -> 分裂出多棵子树 -> 叶子链必须仍产出全局有序
        import random
        rng = random.Random(42)
        keys = list(range(1000))
        rng.shuffle(keys)
        tree = BPlusTree.create(self.db.pager)
        for i in keys:
            tree.insert(k(i), b"x")
        scanned = [key for key, _v in tree.range_scan()]
        self.assertEqual(scanned, [k(i) for i in range(1000)])

    def test_bounded_range(self) -> None:
        tree = BPlusTree.create(self.db.pager)
        for i in range(100):
            tree.insert(k(i), b"x")
        # [10, 20) 左闭右开
        got = [key for key, _ in tree.range_scan(
            start=k(10), end=k(20), start_inclusive=True, end_inclusive=False)]
        self.assertEqual(got, [k(i) for i in range(10, 20)])
        # (10, 20] 左开右闭
        got = [key for key, _ in tree.range_scan(
            start=k(10), end=k(20), start_inclusive=False, end_inclusive=True)]
        self.assertEqual(got, [k(i) for i in range(11, 21)])
        # 点区间 [50, 50]（双闭）恰好包含 50 自己
        got = [key for key, _ in tree.range_scan(
            start=k(50), end=k(50), start_inclusive=True, end_inclusive=True)]
        self.assertEqual(got, [k(50)])
        # 右开的点区间是空的
        got = list(tree.range_scan(
            start=k(50), end=k(50), start_inclusive=True, end_inclusive=False))
        self.assertEqual(got, [])

    def test_root_split_grows_height(self) -> None:
        # 5000 个键必然撑裂根（根起初是叶），高度 +1 且全部可查
        roots: list[int] = []
        tree = BPlusTree.create(
            self.db.pager, on_root_change=lambda r: roots.append(r))
        first_root = tree.root_page
        for i in range(5000):
            tree.insert(k(i), b"x")
        self.assertTrue(roots, "根分裂必须触发 on_root_change 回调")
        self.assertNotEqual(tree.root_page, first_root)
        # 分裂不丢数据：全量扫描 == 全量可查
        self.assertEqual(len(list(tree.range_scan())), 5000)
        for i in (0, 1234, 4999):
            self.assertEqual(tree.search(k(i)), [b"x"])

    def test_delete(self) -> None:
        tree = BPlusTree.create(self.db.pager)
        for i in range(100):
            tree.insert(k(i), b"x")
        self.assertTrue(tree.delete(k(50), b"x"))
        self.assertEqual(tree.search(k(50)), [])
        self.assertEqual(len(list(tree.range_scan())), 99)
        # 删不存在的 (键, 值) 组合：返回 False 而非报错
        self.assertFalse(tree.delete(k(50), b"x"))
        self.assertFalse(tree.delete(k(9999), b"x"))

    def test_delete_during_index_maintenance(self) -> None:
        # 模拟二级索引维护：同键不同值的条目各自精确删除
        tree = BPlusTree.create(self.db.pager)
        tree.insert(k(7), b"rowid-1")
        tree.insert(k(7), b"rowid-2")
        self.assertTrue(tree.delete(k(7), b"rowid-1"))
        self.assertEqual(
            [v for key, v in tree.range_scan(start=k(7), end=k(8))],
            [b"rowid-2"])
        self.assertTrue(tree.delete(k(7), b"rowid-2"))
        self.assertEqual(len(list(tree.range_scan())), 0)


if __name__ == "__main__":      # pragma: no cover
    import unittest
    unittest.main()
