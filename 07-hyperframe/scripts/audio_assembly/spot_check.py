# -*- coding: utf-8 -*-
"""spot_check.py — 抽查 mix_full.wav 关键窗口，验证让位拍编排与句级同步"""
import json, pathlib, subprocess
from faster_whisper import WhisperModel

FF = r"C:\Users\Seven\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
ROOT = pathlib.Path(r"c:\Users\Seven\DeskBox\AI Tools\Cursor Workplace\07-hyperframe")
MIX = ROOT / "assets/audio/mix_full.wav"

def cut(start, dur, out):
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(start), "-t", str(dur),
                    "-i", str(MIX), "-ar", "16000", "-ac", "1", str(out)], check=True)

def main():
    model = WhisperModel("small", device="cpu", compute_type="int8")
    tr = json.loads((ROOT / "transcript.json").read_text(encoding="utf-8"))
    windows = [
        ("拍1前-旁白", 124.0, 8.0),   # 应为 S2 句15 附近旁白
        ("拍1-访谈原声", 131.5, 11.0),  # 应为种植户访谈
        ("拍1后-旁白续", 143.0, 8.0),   # 应为"产业来了…9385…"
        ("拍2-现场讲话", 205.0, 14.0),  # 应为八步沙讲话原声
        ("拍2后-旁白续", 219.5, 7.0),   # 应为"同一片天空下…敦煌"
    ]
    tmp = ROOT / "scripts/audio_assembly"
    print("== 抽查窗口转写 ==")
    for name, st, du in windows:
        wav = tmp / f"spot_{st}.wav"
        cut(st, du, wav)
        segs, _ = model.transcribe(str(wav), language="zh", beam_size=5)
        txt = "".join(s.text for s in segs).strip()
        print(f"\n[{name}] {st}-{st+du}s:\n  {txt}")
        wav.unlink(missing_ok=True)

    # 句级同步定量核对：取 5 个句子边界，转写窗口内首词出现时间 vs transcript 预期
    print("\n== 句级同步核对 ==")
    checks = []
    for sid in ["S1", "S2", "S3"]:
        sents = [s for s in tr["sentences"] if s["seg"] == sid]
        mid = sents[len(sents) // 2]
        checks.append(mid)
    for m in checks:
        st = max(0, m["start_s"] - 2.0)
        wav = tmp / f"sync_{m['start_s']}.wav"
        cut(st, 6.0, wav)
        segs, _ = model.transcribe(str(wav), language="zh", word_timestamps=True, beam_size=5)
        first = None
        for s in segs:
            for w in (s.words or []):
                if w.word.strip():
                    first = w
                    break
            if first:
                break
        got = st + first.start if first else None
        exp = m["start_s"]
        print(f"  {m['seg']}#{m['idx']} 预期 {exp:.2f}s | 实测首词 {got:.2f}s | 偏差 {got-exp:+.2f}s | {m['text'][:18]}")
        wav.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
