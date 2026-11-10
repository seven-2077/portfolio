"""自动演示：脚本回放 3 关预设发射参数。

    python demo.py            # 终端实时渲染（默认）
    python demo.py --fast     # 渲染但不等待帧间隔
    python demo.py --no-render# 只输出文字摘要
    python demo.py --play 2   # 交互模式打第 2 关（键盘输入角度/力度）
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from game import level as lvl
from game import scoring
from game.render import TerminalRenderer, export_svg
from game.sling import Slingshot
from game.world import World

OUT = Path(__file__).resolve().parent / "output"

# 预设发射参数（角度°, 力度 0..1）——脚本回放
PLANS: dict[int, list[tuple[float, float]]] = {
    1: [(52, 0.92), (56, 0.96)],
    2: [(58, 0.94), (52, 0.90), (46, 1.00), (64, 0.94)],
    3: [(58, 0.95), (64, 0.90), (52, 0.90)],
}
FRAME_STEPS = 4  # 每 4 个物理步渲染一帧（120Hz → 30FPS）


def play_shot(
    world: World,
    sling: Slingshot,
    renderer: TerminalRenderer | None,
    hud,
    angle: float,
    power: float,
    fast: bool,
    frame_time: float,
) -> None:
    """拉弓 → 展示瞄准帧 → 发射 → 飞行渲染 → 结算。"""
    state = {"status": "拉弓瞄准", "aim": (angle, power)}
    sling.hold(angle, power)
    if renderer:
        renderer.show(hud(state))
    state.update(status="弹丸飞行", aim=None)
    sling.release(angle, power)
    if renderer is None:
        world.settle()
        return
    n = 0
    while world.shot_active and n < 12000:
        world.step()
        n += 1
        if n % FRAME_STEPS == 0:
            renderer.show(hud(state))
            if not fast:
                time.sleep(frame_time)
    state["status"] = "废墟结算"
    world.settle()
    renderer.show(hud(state))


def run_level(
    spec: lvl.LevelSpec,
    *,
    animate: bool,
    fast: bool,
    interactive: bool,
    frame_time: float,
) -> tuple[scoring.Score, list[str]]:
    """跑完一关，返回（最终得分, 过程摘要行）。"""
    world = World(spec)
    sling = Slingshot(world)
    renderer = TerminalRenderer(world) if animate else None
    log: list[str] = []
    shots = spec.ammo if interactive else len(PLANS[spec.index])

    def hud(state: dict) -> dict:
        counts = Counter(e.material for e in world.events)
        s = scoring.evaluate(counts, world.total_blocks, spec.ammo - world.ammo_spent)
        return {
            "level": spec.index,
            "name": spec.name,
            "score": s.total,
            "ammo_left": spec.ammo - world.ammo_spent,
            "ammo_total": spec.ammo,
            "broken": world.broken,
            "total": world.total_blocks,
            "rate": world.broken / world.total_blocks,
            "status": state.get("status", ""),
            "aim": state.get("aim"),
        }

    for i in range(shots):
        if interactive:
            print(f"\n—— 第 {i + 1}/{shots} 发 ——")
            try:
                angle, power = Slingshot.prompt_aim()
            except (ValueError, EOFError):
                print(" 输入结束，本关收工")
                break
        else:
            angle, power = PLANS[spec.index][i]

        before = Counter(e.material for e in world.events)
        play_shot(world, sling, renderer, hud, angle, power, fast, frame_time)
        after = Counter(e.material for e in world.events)
        gained = {m: after[m] - before[m] for m in after if after[m] > before[m]}
        pts = sum(scoring.POINTS[m] * n for m, n in gained.items())
        n_break = sum(gained.values())
        log.append(
            f"  第{i + 1}发 {angle:.0f}° / {power * 100:.0f}%  →  "
            f"击碎 {n_break} 块（+{pts} 分）"
        )

    if renderer:
        renderer.finish()

    world.settle()
    counts = Counter(e.material for e in world.events)
    score = scoring.evaluate(counts, world.total_blocks, spec.ammo - world.ammo_spent)
    svg = export_svg(
        world,
        OUT / f"level_{spec.index}_result.svg",
        title=f"关卡 {spec.index}：{spec.name} — 废墟图",
        score_line=f"得分 {score.total} · 破坏 {score.broken}/{score.total_blocks} · "
        f"弹丸 {world.ammo_spent}/{spec.ammo}",
        subtitle="Slingshot 物理引擎 · Verlet 积分 · 结构碎裂",
    )
    log.append(
        f"  最终：破坏 {score.broken}/{score.total_blocks} ({score.rate * 100:.0f}%) · "
        f"得分 {score.total} · 弹丸 {world.ammo_spent}/{spec.ammo}"
    )
    log.append(f"  废墟图：output{chr(92)}level_{spec.index}_result.svg")
    return score, log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="愤怒的小鸟式弹弓物理游戏 · 自动演示")
    ap.add_argument("--fast", action="store_true", help="渲染但不等待帧间隔")
    ap.add_argument("--no-render", action="store_true", help="只输出文字摘要")
    ap.add_argument("--level", type=int, choices=(1, 2, 3), help="只跑指定关卡")
    ap.add_argument("--play", type=int, metavar="N", help="交互模式打第 N 关")
    ap.add_argument("--fps", type=float, default=30.0, help="渲染帧率（默认 30）")
    args = ap.parse_args(argv)

    animate = not args.no_render
    frame_time = 1.0 / args.fps if args.fps > 0 else 0.0
    specs = lvl.load_all()

    if args.play:
        specs = [s for s in specs if s.index == args.play]
        if not specs:
            print(f"没有第 {args.play} 关")
            return 1
        specs = [specs[0]]
        args.level = specs[0].index
    elif args.level:
        specs = [s for s in specs if s.index == args.level]

    print("=" * 52)
    print("  弹弓物理演示 · 坍塌是算出来的，不是播出来的")
    print("=" * 52)

    totals: list[tuple[lvl.LevelSpec, scoring.Score]] = []
    try:
        for spec in specs:
            print(f"\n===== 关卡 {spec.index}：{spec.name} =====")
            score, log = run_level(
                spec,
                animate=animate,
                fast=args.fast or not animate,
                interactive=args.play is not None,
                frame_time=frame_time,
            )
            print("\n  过程摘要")
            for line in log:
                print(line)
            totals.append((spec, score))
    except KeyboardInterrupt:
        print("\n（演示中断）")
        return 130

    print("\n" + "=" * 52)
    grand = sum(s.total for _, s in totals)
    rate = sum(s.rate for _, s in totals) / len(totals) * 100 if totals else 0.0
    for spec, s in totals:
        print(
            f"  关卡{spec.index} {spec.name}：破坏 {s.broken}/{s.total_blocks} "
            f"({s.rate * 100:.0f}%) · {s.total} 分"
        )
    print(f"  总得分 {grand} · 平均破坏率 {rate:.0f}%")
    print(f"  SVG 产物：{OUT}")
    print("=" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
