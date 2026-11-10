"""pet.interact — 终端交互循环。

Windows 下 msvcrt 非阻塞轮询按键，空闲时原地刷新时钟；非 TTY（管道/测试）
自动走「固定步数演示模式」。render() 输出时间、状态条、学习加成与形象。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from . import engine, growth, persist, sprites, studylink
from .engine import PetState
from .studylink import StudyReport

try:
    import msvcrt          # Windows 专用；非 Windows 上为 None
except ImportError:        # pragma: no cover
    msvcrt = None

STATUS_ZH = {"idle": "空闲", "eating": "吃饭中", "playing": "玩耍中",
             "sleeping": "睡觉中", "sick": "生病中"}
BAR_WIDTH = 18
KEYS = "1234q"
DEFAULT_SCRIPT = ("feed", "play", "status", "sleep", "wake", "feed")


def bar(value: float, width: int = BAR_WIDTH) -> str:
    """0-100 → █/░ 状态条。"""
    filled = round(max(0.0, min(100.0, value)) * width / 100)
    return "█" * filled + "░" * (width - filled)


def fmt_duration(seconds: float) -> str:
    """秒 → '1d3h' / '3h12m' / '45s'。"""
    s = int(max(0, seconds))
    if s >= 86400:
        return f"{s // 86400}d{s % 86400 // 3600}h"
    if s >= 3600:
        return f"{s // 3600}h{s % 3600 // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


def study_line(report: StudyReport | None) -> str:
    if report is None:
        return " 📚 学习数据：未加载"
    bonus = round(report.bonus * 100)
    if report.source == "demo":
        return (f" 📚 今日学习 {studylink.format_minutes(report.minutes)}"
                f"（演示数据）→ 喂食加成 +{bonus}%")
    return (f" 📚 今日学习 {studylink.format_minutes(report.minutes)}"
            f" → 喂食加成 +{bonus}%（study-timer）")


def render(pet: PetState, report: StudyReport | None = None,
           now: float | None = None, frame: int = 0) -> str:
    """渲染完整界面：顶部信息 + 四条状态条 + 学习加成 + 形象 + 菜单。"""
    now = time.time() if now is None else now
    stage = growth.stage_at(pet.stage_idx)
    fullness = 100 - pet.hunger
    sprite = sprites.get_sprite(stage.key, pet.mood, frame,
                                sleeping=pet.status == engine.SLEEPING)
    return "\n".join([
        "═════════════ virtual-pet ═════════════",
        f" 🕐 {datetime.fromtimestamp(now):%Y-%m-%d %H:%M:%S}"
        f"   [{stage.name}] {pet.name}"
        f"   状态：{STATUS_ZH.get(pet.status, pet.status)}",
        f" 饱食 {bar(fullness)} {round(fullness)}",
        f" 心情 {bar(pet.mood)} {round(pet.mood)}",
        f" 能量 {bar(pet.energy)} {round(pet.energy)}",
        f" 健康 {bar(pet.health)} {round(pet.health)}",
        study_line(report),
        "",
        sprite,
        "",
        " [1]喂食  [2]玩耍  [3]睡觉/叫醒  [4]详情  [q]保存退出",
    ])


def detail(pet: PetState, report: StudyReport | None = None,
           save_path=None) -> str:
    """[4] 详情页：阶段说明、年龄、压力计时、学习数据来源。"""
    stage = growth.stage_at(pet.stage_idx)
    lines = [
        " ── 详情 ─────────────────────────────",
        f" 名字：{pet.name}   阶段：{stage.name}（{stage.desc}）",
        f" 年龄：{fmt_duration(pet.age_seconds)}"
        f"   下一阶段还需健康 ≥ {growth.GROW_MIN_HEALTH} 才能晋升",
        f" 压力累计：{fmt_duration(pet.stress_seconds)}"
        f" / 阈值 {fmt_duration(engine.STRESS_SECONDS)}",
        f" 饥饿警戒线（本阶段）：{round(stage.hunger_danger)}",
    ]
    if report is not None:
        src = report.log_path or f"内置演示数据（+{round(report.bonus * 100)}%）"
        lines.append(f" 学习来源：{src}")
    if save_path:
        lines.append(f" 存档：{save_path}")
    lines.append(" ─────────────────────────────────────")
    return "\n".join(lines)


def read_key(timeout: float = 1.0, sleep_fn=time.sleep) -> str | None:
    """非阻塞读键：timeout 内无按键返回 None。无 msvcrt 环境同样返回 None。"""
    if msvcrt is None:
        sleep_fn(timeout)
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if msvcrt.kbhit():
            raw = msvcrt.getch()
            try:
                return raw.decode("ascii").lower()
            except UnicodeDecodeError:
                return None        # 方向键等扩展序列：忽略
        sleep_fn(0.05)
    return None


def _do_action(pet: PetState, name: str,
               report: StudyReport | None) -> engine.Action:
    bonus = report.bonus if report else 0.0
    if name == "feed":
        return engine.feed(pet, bonus)
    if name == "play":
        return engine.play(pet, bonus)
    if name == "sleep":
        return engine.sleep(pet)
    if name == "wake":
        return engine.wake(pet)
    if name == "status":
        return engine.Action(True, detail(pet, report))
    return engine.Action(False, f"未知动作：{name}")


def _run_script(pet: PetState, steps: int, script, report, now_fn, out):
    """固定步数演示模式（非 TTY / 测试用）：逐步执行脚本并打印日志。"""
    out(render(pet, report, now=now_fn()))
    log: list[str] = []
    for i in range(steps):
        name = script[i % len(script)]
        for event in engine.advance(pet, now_fn()):
            line = f"  ✨ {event}"
            out(line)
            log.append(line)
        if name == "3" and pet.status == engine.SLEEPING:
            result = engine.wake(pet)
        else:
            action = {"1": "feed", "2": "play", "3": "sleep"}.get(name, name)
            result = _do_action(pet, action, report)
        line = f"[{i + 1:>2}] {action_name(name)}：{result.message}"
        out(line)
        log.append(line)
        out(render(pet, report, now=now_fn(), frame=i % 2))
        out("─" * 46)
    return log


def action_name(key: str) -> str:
    return {"1": "喂食", "2": "玩耍", "3": "睡觉", "4": "详情",
            "feed": "喂食", "play": "玩耍", "sleep": "睡觉",
            "wake": "醒来", "status": "状态"}.get(key, key)


def _run_interactive(pet: PetState, report, now_fn, sleep_fn, out):
    """交互循环：msvcrt 非阻塞轮询；空闲时原地刷新时钟行。"""
    out(render(pet, report, now=now_fn()))
    while True:
        for event in engine.advance(pet, now_fn()):
            out(f"  ✨ {event}")
            out(render(pet, report, now=now_fn(),
                       frame=int(now_fn()) % 2))
        key = read_key(timeout=1.0, sleep_fn=sleep_fn)
        if key is None:
            stamp = datetime.fromtimestamp(now_fn()).strftime("%H:%M:%S")
            out(f"\r ⏱ {stamp}  [1]喂食 [2]玩耍 [3]睡觉 [4]详情 [q]退出"
                f"        ", end="")
            continue
        out("\r" + " " * 66 + "\r", end="")
        if key == "q":
            out("它恋恋不舍地蹭了蹭你的手。")
            return
        if key not in KEYS:
            out(f" 未知按键：{key!r}（可用：{'/'.join(KEYS)}）")
            continue
        if key == "4":
            out(detail(pet, report))
            continue
        if key == "3" and pet.status == engine.SLEEPING:
            result = engine.wake(pet)
        else:
            result = _do_action(pet, {"1": "feed", "2": "play",
                                      "3": "sleep"}[key], report)
        out(f" {result.message}")
        out(render(pet, report, now=now_fn(), frame=int(now_fn()) % 2))


def run(pet: PetState, save_path=None, steps: int | None = None,
        script=DEFAULT_SCRIPT, now_fn=time.time, sleep_fn=time.sleep,
        out=print) -> list[str]:
    """主入口。steps 给定或非 TTY → 固定步数演示；否则交互循环。

    退出时若给了 save_path 则自动存档。返回演示模式的动作日志。
    """
    report = studylink.load_report()
    interactive = steps is None and msvcrt is not None and sys.stdin.isatty()
    log: list[str] = []
    try:
        if interactive:
            _run_interactive(pet, report, now_fn, sleep_fn, out)
        else:
            log = _run_script(pet, steps or len(script), script,
                              report, now_fn, out)
    finally:
        if save_path:
            path = persist.save(pet, save_path)
            out(f" 💾 已存档：{path}")
    return log


def main() -> None:
    pet = persist.load() or engine.new_pet()
    print("欢迎回来！（按键：1 喂食 · 2 玩耍 · 3 睡觉 · 4 详情 · q 退出）")
    run(pet, save_path=persist.DEFAULT_PATH)


if __name__ == "__main__":
    main()
