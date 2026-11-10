#!/usr/bin/env python3
"""一键演示：时间加速模拟一整天的演化（喂食 → 成长 → 状态变化）。

    python demo.py              # 文本日志，虚拟 24h（48 步 × 30min）
    python demo.py --snapshot   # 额外输出 output/day_snapshot.bmp 快照图
    python demo.py --steps 12   # 只跑 12 步快速看效果

日志同时落盘到 output/day_log.txt。时间由注入的虚拟时钟驱动，
引擎走的是和正式游玩完全相同的 advance() 结算路径。
"""

from __future__ import annotations

import argparse
import struct
import time
from pathlib import Path

from pet import engine, growth, studylink
from pet.interact import STATUS_ZH, fmt_duration, render, study_line

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
LOG_FILE = OUTPUT_DIR / "day_log.txt"
SNAPSHOT_FILE = OUTPUT_DIR / "day_snapshot.bmp"

STEP_SECONDS = 1800          # 每步虚拟 30 分钟
START_CLOCK = 8 * 3600        # 虚拟一天从 08:00 开始

# (第几步 → 动作)：晨间喂玩透支能量 → 中午摆烂到病倒 → 救回来 → 安稳入睡
TIMELINE = {
    1: "feed", 3: "play", 5: "play", 8: "play", 10: "play", 12: "play",
    28: "feed", 29: "sleep", 36: "wake", 37: "feed", 39: "play",
    43: "feed", 44: "play", 45: "sleep",
}


def _clock(vnow: float, t0: float) -> str:
    """虚拟时刻 HH:MM（从 08:00 起算，纯算术避免时区偏移）。"""
    secs = int(vnow - t0 + START_CLOCK) % 86400
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}"


def _status_line(step: int, pet: engine.PetState, t0: float) -> str:
    stage = growth.stage_at(pet.stage_idx)
    return (f"[{step:>2}] {_clock(pet.last_tick, t0)} "
            f"| {stage.name} | 饱 {round(100 - pet.hunger):>3} "
            f"心 {round(pet.mood):>3} 能 {round(pet.energy):>3} "
            f"康 {round(pet.health):>3} | {STATUS_ZH[pet.status]}")


def action_name(action: str) -> str:
    return {"feed": "喂食", "play": "玩耍", "sleep": "睡觉",
            "wake": "叫醒"}[action]


def simulate(steps: int = 48, out=print) -> engine.PetState:
    """跑一遍压缩时间的一天，打印日志，返回最终宠物状态。"""
    report = studylink.load_report()
    pet = engine.new_pet("小煤球")
    t0 = pet.born_at
    lines: list[str] = []
    grow_stages: list[str] = [growth.stage_at(0).name]
    actions = events = 0

    def emit(text: str = "") -> None:
        lines.append(text)
        out(text)

    emit(f"🎮 时间加速开始：{steps} 步 × 30min = 虚拟 "
         f"{fmt_duration(steps * STEP_SECONDS)}")
    emit(study_line(report))
    emit(render(pet, report, now=t0))
    emit("─" * 46)

    for step in range(1, steps + 1):
        vnow = t0 + step * STEP_SECONDS
        for event in engine.advance(pet, vnow):
            events += 1
            emit(f"  ✨ {event}")
            if "→" in event:
                grow_stages.append(event.split(" → ")[1].split("！")[0])
        action = TIMELINE.get(step)
        if action:
            actions += 1
            if action == "sleep":
                result = engine.sleep(pet)
            elif action == "wake":
                result = engine.wake(pet)
            elif action == "feed":
                result = engine.feed(pet, report.bonus)
            else:
                result = engine.play(pet, report.bonus)
            emit(f"  ▶ {action_name(action)}：{result.message}")
        emit(_status_line(step, pet, t0))
        if step % 12 == 0 and step != steps:
            emit(render(pet, report, now=vnow, frame=step % 2))
        emit()

    emit("═" * 46)
    emit(render(pet, report, now=t0 + steps * STEP_SECONDS,
                frame=steps % 2))
    emit(f"🏁 模拟结束：虚拟时长 {fmt_duration(steps * STEP_SECONDS)}"
         f"，阶段历程 {' → '.join(grow_stages)}")
    emit(f"   玩家动作 {actions} 次，事件 {events} 条，"
         f"最终年龄 {fmt_duration(pet.age_seconds)}")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("\n".join(lines), encoding="utf-8")
    return pet


# ---------- 状态快照图（24-bit BMP，纯 struct 手写） ----------

_W, _H = 480, 270
_COLORS = {                      # 饱食/心情/能量/健康
    "full": (56, 168, 255), "mood": (255, 118, 177),
    "energy": (255, 196, 61), "health": (110, 220, 128),
}
_BG = (30, 32, 40)
_TRACK = (54, 57, 68)
_AGE_BAR = (190, 160, 255)


def snapshot_pixels(pet: engine.PetState) -> list[list[tuple[int, int, int]]]:
    """把最终状态画成背景 + 4 条状态柱 + 4 个阶段指示灯（顶行在前）。"""
    px = [[_BG] * _W for _ in range(_H)]

    def rect(x: int, y: int, w: int, h: int, color) -> None:
        for yy in range(max(0, y), min(_H, y + h)):
            row = px[yy]
            for xx in range(max(0, x), min(_W, x + w)):
                row[xx] = color

    # 顶部阶段指示灯（点亮到当前阶段）
    for i, st in enumerate(growth.STAGES):
        rect(24 + i * 28, 18, 18, 18,
             (255, 220, 90) if i <= pet.stage_idx else (66, 68, 78))
    # 四条状态柱
    values = ((100 - pet.hunger, _COLORS["full"]), (pet.mood, _COLORS["mood"]),
              (pet.energy, _COLORS["energy"]), (pet.health, _COLORS["health"]))
    for i, (value, color) in enumerate(values):
        y = 56 + i * 46
        rect(24, y, 420, 28, _TRACK)
        rect(24, y, round(420 * value / 100), 28, color)
        rect(450, y, 4, 28, color)           # 右侧色标
    # 底部：年龄进度条（按最老阶段 18h 归一）+ 阶段分界刻度
    rect(24, _H - 34, 432, 10, _TRACK)
    span = growth.STAGES[-1].min_age
    rect(24, _H - 34, round(432 * min(1.0, pet.age_seconds / span)),
         10, _AGE_BAR)
    for st in growth.STAGES[1:]:
        rect(24 + round(432 * st.min_age / span), _H - 38, 2, 18,
             (230, 230, 240))
    rect(0, _H - 4, _W, 4, _AGE_BAR)
    return px


def write_bmp(path: Path, pixels) -> Path:
    """把像素（顶行在前）写成 24-bit BMP。"""
    height, width = len(pixels), len(pixels[0])
    row_pad = (4 - (width * 3) % 4) % 4
    body = bytearray()
    for row in reversed(pixels):            # BMP 自底向上存储
        for b, g, r in row:                 # 输入 (r,g,b)，落盘为 BGR
            body += bytes((b, g, r))
        body += b"\x00" * row_pad
    size = 54 + len(body)
    header = struct.pack("<2sIHHI", b"BM", size, 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                      len(body), 2835, 2835, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + dib + bytes(body))
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="virtual-pet 一天演化演示")
    parser.add_argument("--steps", type=int, default=48,
                        help="模拟步数（默认 48 步 = 虚拟 24h）")
    parser.add_argument("--snapshot", action="store_true",
                        help=f"输出状态快照图 {SNAPSHOT_FILE.name}")
    args = parser.parse_args(argv)

    started = time.time()
    pet = simulate(steps=args.steps)
    if args.snapshot:
        path = write_bmp(SNAPSHOT_FILE, snapshot_pixels(pet))
        print(f"🖼  快照图已输出：{path}")
    print(f"📄 文本日志：{LOG_FILE}（耗时 {time.time() - started:.2f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
