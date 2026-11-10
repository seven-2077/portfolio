#!/usr/bin/env python3
"""raycast-fps 演示与交互入口。

用法（项目根目录）::

    python demo.py               # 交互模式：WASD 移动，空格开火，Q 退出
    python demo.py --demo        # 自动巡游：预录输入走完地图并开几枪，
                                 # 全程帧序列录制到 output/demo_frames.txt
    python demo.py --demo --map vault --show    # 换张图并实时观看
    python demo.py --demo --no-record           # 只统计，不写文件

录制产物（全部在项目内 ``output/``）::

    demo_frames.txt    完整帧序列（每帧以 ===== FRAME n ===== 分隔）
    demo_preview.txt   抽帧预览（首帧 / 均匀采样 / 末帧）
    demo_summary.txt   巡游统计（帧数、耗时、帧率、覆盖率、击杀、得分）
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from typing import List, Optional, Set, Tuple

from fps.loop import Game, ScriptedInput, make_game, run
from fps.player import KeyReader

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SIM_FPS = 30.0            # 巡游按固定 30Hz 步进，与录制帧一一对应


def build_script() -> List[Tuple[Set[str], int]]:
    """预录输入序列：左侧走廊 → 南下拾取 → 中廊东进 → 出口 →
    右侧长廊 → 中央暗室（敌人老巢）开火。"""
    return [
        ({"forward"}, 40),            # 出生后面朝南，沿左走廊下到底
        ({"turn_l"}, 18),             # 面向东
        ({"forward"}, 24),            # 走到第 4 列前
        ({"turn_r"}, 18),             # 面向南
        ({"forward"}, 20),            # 下到第 7 行
        ({"turn_r"}, 18),             # 面向西
        ({"forward"}, 25),            # 贴走廊西侧
        ({"turn_l"}, 18),             # 面向南
        ({"forward"}, 60),            # 一路南下（捡左下弹药）
        ({"turn_l"}, 18),             # 面向东
        ({"forward"}, 17),            # 到第 2 列
        ({"turn_l"}, 18),             # 面向北
        ({"forward"}, 25),            # 北上到中廊
        ({"turn_r"}, 18),             # 面向东
        ({"forward", "shoot"}, 45),   # 东进（捡医疗包，顺手两枪）
        ({"turn_l"}, 18),             # 面向北
        ({"forward"}, 96),            # 沿中央竖廊穿到顶
        ({"turn_r"}, 18),             # 面向东
        ({"forward", "shoot"}, 78),   # 走完北侧横廊（捡弹药、踏上出口）
        ({"turn_r"}, 18),             # 面向南
        ({"forward"}, 70),            # 下右侧长廊
        ({"forward", "shoot"}, 50),   # 继续南下并开火
        ({"turn_r"}, 18),             # 面向西
        ({"forward"}, 17),            # 底部向西一步
        ({"turn_r"}, 18),             # 面向北
        ({"forward", "shoot"}, 26),   # 北上到第 11 行（巡逻怪老家）
        ({"turn_l"}, 18),             # 面向西
        ({"forward"}, 12),            # 挪到第 12 列
        ({"turn_r"}, 18),             # 面向北
        ({"forward"}, 36),            # 沿第 12 列北上到第 7 行
        ({"turn_l"}, 18),             # 面向西
        ({"forward"}, 30),            # 西行到暗室入口上方
        ({"turn_l"}, 18),             # 面向南
        ({"forward", "shoot"}, 60),   # 钻进暗室一路开火
        ({"turn_r"}, 36),             # 原地掉头向北
        ({"forward"}, 65),            # 撤回入口，巡游结束
        ({"turn_r", "shoot"}, 72),    # 边转身边开火清扫一圈 → 收掉尾随哨兵
    ]


def _write_record(path: str, frames: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for index, frame in enumerate(frames):
            handle.write(f"===== FRAME {index:04d} =====\n{frame}\n")


def _write_preview(path: str, frames: List[str], samples: int = 8) -> None:
    if not frames:
        return
    step = max(1, len(frames) // samples)
    picked = list(range(0, len(frames), step))[-samples:]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for index in picked:
            handle.write(f"----- frame {index:04d} -----\n{frames[index]}\n")


def _summary(game: Game, stats: dict, map_name: str) -> str:
    floor_total = len(game.gmap.floor_cells())
    seen = len(game.visited)
    killed = len(game.enemies) - game.alive_enemies
    outcome = {"win": "通关", "lose": "失败"}.get(game.status or "", "进行中")
    lines = [
        "raycast-fps 自动巡游统计",
        "=" * 46,
        f"地图          {map_name}（{game.gmap.width}×{game.gmap.height}）",
        f"渲染帧数      {int(stats['frames'])}",
        f"实际耗时      {stats['elapsed'] * 1000:.0f} ms",
        f"实测帧率      {stats['fps']:.1f} fps（纯渲染吞吐，无 sleep）",
        f"模拟时长      {stats['frames'] / SIM_FPS:.1f} s @ {SIM_FPS:.0f} Hz",
        f"探索覆盖      {seen}/{floor_total} 格"
        f"（{seen / max(1, floor_total) * 100:.1f}%）",
        f"击杀          {killed}/{len(game.enemies)}",
        f"出口          {'已抵达' if game.exit_taken else '未抵达'}",
        f"剩余血量      {game.player.hp}",
        f"弹药          {game.player.ammo}",
        f"最终得分      {game.player.score}",
        f"结局          {outcome}",
    ]
    return "\n".join(lines)


def run_demo(args) -> int:
    game = make_game(args.map, seed=args.seed,
                     width=args.width, height=args.height)
    total = sum(n for _, n in build_script())
    source = ScriptedInput(build_script(), quit_when_done=True)
    frames: List[str] = []
    record = not args.no_record

    def on_frame(index: int, frame: str) -> None:
        if record:
            frames.append(frame)

    print("=" * 52)
    print(" raycast-fps · 自动巡游演示（预录输入，30 Hz 步进）")
    print("=" * 52)
    started = time.perf_counter()
    stats = run(game, input_source=source, target_fps=SIM_FPS,
                show=args.show, realtime=args.show,
                max_frames=args.frames if args.frames else total,
                on_frame=on_frame)
    wall = time.perf_counter() - started

    summary = _summary(game, stats, args.map)
    print(summary)
    print(f"\n总耗时（含录制） {wall * 1000:.0f} ms")
    if record:
        os.makedirs(OUT_DIR, exist_ok=True)
        if frames:
            _write_record(os.path.join(OUT_DIR, "demo_frames.txt"), frames)
            _write_preview(os.path.join(OUT_DIR, "demo_preview.txt"), frames)
            print(f"帧序列已录制 → output/demo_frames.txt（{len(frames)} 帧）")
        with open(os.path.join(OUT_DIR, "demo_summary.txt"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(summary + "\n")
    return 0


def run_interactive(args) -> int:
    size = shutil.get_terminal_size()
    if size.lines < args.height or size.columns < args.width:
        print(f"提示：终端当前 {size.columns}×{size.lines}，"
              f"建议放大到至少 {args.width}×{args.height} 再玩。")
    game = make_game(args.map, seed=args.seed,
                     width=args.width, height=args.height)
    print("=" * 52)
    print(" raycast-fps · 终端迷宫射击")
    print("  [WASD] 移动   [←→ / J L] 转头   [空格] 开火")
    print("  [M] 小地图开关   [Q] 退出   （清光敌人即通关）")
    print("=" * 52)
    try:
        stats = run(game, input_source=KeyReader(), target_fps=args.fps,
                    show=True, realtime=True)
    except KeyboardInterrupt:
        print("\n已中断。")
        return 0
    print(f"\n本局 {int(stats['frames'])} 帧 · 平均 {stats['fps']:.1f} fps · "
          f"得分 {game.player.score} · "
          f"{'通关！' if game.status == 'win' else '再来一局？'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="raycast-fps：终端伪 3D 迷宫射击")
    parser.add_argument("--demo", action="store_true",
                        help="自动巡游模式（预录输入走完地图并开枪）")
    parser.add_argument("--map", default="crypt",
                        choices=["crypt", "vault", "random"],
                        help="地图（默认 crypt；random 按 seed 生成）")
    parser.add_argument("--seed", type=int, default=7,
                        help="random 地图种子（默认 7）")
    parser.add_argument("--width", type=int, default=80,
                        help="画面宽度（默认 80）")
    parser.add_argument("--height", type=int, default=24,
                        help="画面高度（默认 24）")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="交互模式目标帧率（默认 30）")
    parser.add_argument("--frames", type=int, default=None,
                        help="demo 模式最多跑多少帧（默认走完脚本）")
    parser.add_argument("--show", action="store_true",
                        help="demo 模式把帧实时打到终端")
    parser.add_argument("--no-record", action="store_true",
                        help="demo 模式不写 output/ 录制文件")
    args = parser.parse_args(argv)
    if args.height < 8 or args.width < 32:
        parser.error("画面太小：至少 32×8")
    return run_demo(args) if args.demo else run_interactive(args)


if __name__ == "__main__":
    sys.exit(main())
