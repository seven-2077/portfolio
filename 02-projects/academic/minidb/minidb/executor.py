"""执行器：驱动算子树直到耗尽，收集结果。

执行器本身薄得只剩「拉取循环」—— 这正是 Volcano 模型的要点：
所有工作都在算子里，编排只有一层 ``open -> while next -> close``。
"""

from __future__ import annotations

from .operators import DeleteOp, InsertOp, Operator, UpdateOp


class Executor:
    """把算子树跑干。"""

    @staticmethod
    def run(plan: Operator) -> tuple[list[tuple], int]:
        """执行计划，返回 (结果行, 行数)。

        DML 算子的 next() 返回 None 但内部已完成写入，
        行数要问算子自己；SELECT 则以产出的行数为准。
        """
        rows: list[tuple] = []
        plan.open()
        try:
            while True:
                row = plan.next()
                if row is None:
                    break
                rows.append(row.values)
        finally:
            plan.close()

        if isinstance(plan, (InsertOp, UpdateOp, DeleteOp)):
            return rows, plan.rowcount()
        return rows, len(rows)
