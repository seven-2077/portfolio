#!/usr/bin/env python3
"""mimo-v2.5-tts 分段配音合成器（零依赖，仅标准库）

按 SCRIPT.md 的 S0..Sn 分段合成口播配音，输出到 assets/audio/，
并打印每段时长——这张时长表就是下一步 transcript.json 时间戳的原料。

用法:
  python tools/tts_synthesize.py --list                 # 列出分段与字数
  python tools/tts_synthesize.py --only S0 --voice 冰糖  # 试听单段（选音色用）
  python tools/tts_synthesize.py --voice 白桦            # 全部分段合成
  python tools/tts_synthesize.py --design "深沉浑厚的纪录片旁白男声" --only S0
                                                         # voicedesign 按描述设计音色

环境变量:
  MIMO_API_KEY（或 XIAOMI_API_KEY）  必填，MiMo 控制台获取
  MIMO_TTS_URL                       可选，默认按量接口；
                                     套餐(Token Plan)用户设为
                                     https://token-plan-cn.xiaomimimo.com/v1/chat/completions
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_MD = ROOT / "SCRIPT.md"
AUDIO_DIR = ROOT / "assets" / "audio"

DEFAULT_URL = "https://api.xiaomimimo.com/v1/chat/completions"
DEFAULT_VOICE = "白桦"
DEFAULT_STYLE = (
    "沉稳庄重的纪录片旁白，男声，语速平缓，叙事感强，"
    "情绪克制而有力量，字正腔圆"
)
PRESET_VOICES = ["mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]


def parse_segments(md_text: str) -> dict:
    """按 ### Sx 标题切出口播段；片尾字幕标注不上口播，直接截断。"""
    segs, cur, buf = {}, None, []
    for line in md_text.splitlines():
        m = re.match(r"^### (S\d)\s", line)
        if m:
            if cur is not None:
                segs[cur] = " ".join(buf).strip()
            cur, buf = m.group(1), []
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("（片尾"):
            segs[cur] = " ".join(buf).strip()
            cur, buf = None, []
            continue
        if s:
            buf.append(s)
    if cur is not None:
        segs[cur] = " ".join(buf).strip()
    return {k: v for k, v in segs.items() if v}


def env_file_value(name: str):
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == name and v.strip():
                    return v.strip().strip('"').strip("'")
    return None


def api_key() -> str:
    key = (os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_API_KEY")
           or env_file_value("MIMO_API_KEY") or env_file_value("XIAOMI_API_KEY"))
    if key:
        return key
    sys.exit("缺少 API Key：设置环境变量 MIMO_API_KEY，或在项目根 .env 里填写（已 gitignore）")


def synth(text, *, style, voice, design, ref_audio, url, key, model):
    if design:  # voicedesign：user 消息必填为音色描述，不传 audio.voice
        messages = [{"role": "user", "content": design + "。" + style},
                    {"role": "assistant", "content": text}]
        audio = {"format": "wav"}
    elif ref_audio:  # voiceclone：voice 传参考音频 base64
        b64 = base64.b64encode(ref_audio.read_bytes()).decode()
        mime = "audio/mpeg" if ref_audio.suffix.lower() == ".mp3" else "audio/wav"
        messages = [{"role": "user", "content": style},
                    {"role": "assistant", "content": text}]
        audio = {"format": "wav", "voice": "data:" + mime + ";base64," + b64}
    else:  # 预置音色
        messages = [{"role": "user", "content": style},
                    {"role": "assistant", "content": text}]
        audio = {"format": "wav", "voice": voice}

    payload = {"model": model, "messages": messages, "audio": audio}
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "api-key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit("API 错误 " + str(e.code) + ": " + body[:800])
    try:
        return base64.b64decode(out["choices"][0]["message"]["audio"]["data"])
    except (KeyError, IndexError, TypeError):
        sys.exit("响应结构异常: " + json.dumps(out, ensure_ascii=False)[:800])


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    ap = argparse.ArgumentParser(description="SCRIPT.md -> assets/audio/ 分段配音")
    ap.add_argument("--only", metavar="S0", help="只合成这一段")
    ap.add_argument("--voice", default=DEFAULT_VOICE,
                    help="预置音色，可选: " + ", ".join(PRESET_VOICES))
    ap.add_argument("--style", default=DEFAULT_STYLE, help="语气风格指令（不进入合成文本）")
    ap.add_argument("--design", help="voicedesign：用文字描述设计音色")
    ap.add_argument("--ref", type=Path, help="voiceclone：参考音频路径（mp3/wav）")
    ap.add_argument("--model", default=None, help="模型 ID，默认按参数自动选择")
    ap.add_argument("--url", default=None)
    ap.add_argument("--list", action="store_true", help="只列出分段不合成")
    args = ap.parse_args()
    args.url = (args.url or os.environ.get("MIMO_TTS_URL")
                or env_file_value("MIMO_TTS_URL") or DEFAULT_URL)

    if args.model is None:
        args.model = ("mimo-v2.5-tts-voiceclone" if args.ref else
                      "mimo-v2.5-tts-voicedesign" if args.design else
                      "mimo-v2.5-tts")

    segs = parse_segments(SCRIPT_MD.read_text(encoding="utf-8"))
    if not segs:
        sys.exit("SCRIPT.md 里没有解析到 S 段")
    if args.only:
        if args.only not in segs:
            sys.exit("没有 " + args.only + "，可选: " + ", ".join(segs))
        segs = {args.only: segs[args.only]}

    if args.list:
        for k, v in segs.items():
            print(k + ": " + str(len(v)) + " 字  " + v[:40] + "...")
        return

    key = api_key()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    total, rows = 0.0, []
    for name, text in segs.items():
        print("[" + name + "] 合成中 (" + str(len(text)) + " 字, model=" + args.model + ") ...", flush=True)
        data = synth(text, style=args.style, voice=args.voice,
                     design=args.design, ref_audio=args.ref,
                     url=args.url, key=key, model=args.model)
        out = AUDIO_DIR / (name + ".wav")
        out.write_bytes(data)
        d = wav_duration(out)
        total += d
        rows.append((name, len(text), d))
        print("        -> " + out.name + "  " + format(d, ".2f") + "s")

    print("")
    print("段落        字数    时长      累计")
    cum = 0.0
    for name, n, d in rows:
        cum += d
        print("{:<10} {:<6} {:>7.2f}s  {:>7.2f}s".format(name, n, d, cum))
    print("总时长 " + format(total, ".2f") + "s（" + format(total / 60, ".1f") + " 分钟）")
    print("下一步：用这张时长表生成 transcript.json 时间戳。")


if __name__ == "__main__":
    main()