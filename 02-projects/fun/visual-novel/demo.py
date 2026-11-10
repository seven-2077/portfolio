#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""demo 入口 —— 自动走完一条结局路线，或交互试玩。

    python demo.py                 # 自动演示：全程选第 1 项，写 output/playthrough.txt
    python demo.py --play          # 交互模式（回车继续 / 选项输入 / s N 存档 ...）
    python demo.py --instant       # 关掉打字机节奏，瞬间出产物
    python demo.py --cps 60        # 指定打字速度（字符/秒）
    python demo.py --no-color      # 关闭 ANSI 配色
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vn import Engine, EngineConfig, KeyPoller, Renderer, Script, ScriptError, strip_ansi

ROOT = Path(__file__).resolve().parent
DEFAULT_SCRIPT = ROOT / "story" / "rain_signal.vn"
DEFAULT_OUT = ROOT / "output" / "playthrough.txt"
DEFAULT_SAVES = ROOT / "output" / "saves"


class _StripStream:
    """写入前剥掉 ANSI 序列——保证产物 playthrough.txt 是纯文本。"""

    def __init__(self, fp):
        self._fp = fp

    def write(self, s: str) -> int:
        return self._fp.write(strip_ansi(s))

    def flush(self) -> None:
        self._fp.flush()

    def isatty(self) -> bool:
        return False


class _Tee:
    """同时写到终端与文件的流（用于自动演示全程留档）。"""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, s: str) -> int:
        for st in self._streams:
            st.write(s)
        return len(s)

    def flush(self) -> None:
        for st in self._streams:
            st.flush()

    def isatty(self) -> bool:
        return any(getattr(st, "isatty", lambda: False)() for st in self._streams)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="vn 终端视觉小说 —— demo 驱动器")
    p.add_argument("--play", action="store_true", help="交互试玩模式")
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT, help="剧本路径")
    p.add_argument("--cps", type=float, default=40.0, help="打字机速度（字符/秒，<=0 为瞬时）")
    p.add_argument("--instant", action="store_true", help="瞬时输出（等价 --cps 0）")
    p.add_argument("--no-color", action="store_true", help="关闭 ANSI 配色")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="自动演示的全程文本输出路径")
    p.add_argument("--save-dir", type=Path, default=DEFAULT_SAVES, help="存档槽目录")
    return p


def load_script(path: Path):
    try:
        return Script.from_file(path)
    except ScriptError as exc:
        print(f"剧本解析失败：{exc}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as exc:
        print(f"无法读取剧本 {path}：{exc}", file=sys.stderr)
        raise SystemExit(2)


def run_auto(args) -> int:
    """自动演示：autoplay + 全程选第 1 项，双写终端与 playthrough.txt。"""
    script = load_script(args.script)
    cps = 0.0 if args.instant else args.cps
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fp:
        tee = _Tee(sys.stdout, _StripStream(fp))
        renderer = Renderer(stream=tee, color=False if args.no_color else None,
                            cps=cps)
        config = EngineConfig(cps=cps, autoplay=True,
                              save_dir=str(args.save_dir))
        engine = Engine(script, renderer=renderer, config=config)
        ending = engine.run()
    print(f"  ▶ 自动路线达成结局：{ending or '（未完成）'}")
    print(f"  ▶ 全程文本 → {args.out}")
    print(f"  ▶ 想自己玩：python demo.py --play")
    return 0


def run_play(args) -> int:
    """交互模式：真实输入 + 打字跳过按键。"""
    script = load_script(args.script)
    cps = 0.0 if args.instant else args.cps
    color = False if args.no_color else None
    key_poll = KeyPoller()
    try:
        renderer = Renderer(color=color, cps=cps, key_poll=key_poll.poll)
        config = EngineConfig(cps=cps, autoplay=False,
                              save_dir=str(args.save_dir))
        engine = Engine(script, renderer=renderer, config=config)
        ending = engine.run()
    finally:
        key_poll.close()
    if ending:
        print(f"  ▶ 达成结局：{ending}")
        print("  ▶ 想换条路线试试？再来一局 python demo.py --play")
    else:
        print("  ▶ 本局中断。下次可从存档继续（提示处输入 l N）。")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run_play(args) if args.play else run_auto(args)


if __name__ == "__main__":
    raise SystemExit(main())
