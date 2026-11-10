# -*- coding: utf-8 -*-
"""align.py — 对男声旁白做词级转写，与 transcript.json 已知句文本对齐，输出每句起止。

输出: scripts/audio_assembly/male_sentence_times.json
      { "S0": [{"idx":1,"start":0.0,"end":5.3}, ...], ... }  (时间相对各段 wav)
"""
import json, re, difflib, pathlib
from faster_whisper import WhisperModel

ROOT = pathlib.Path(r"c:\Users\Seven\DeskBox\AI Tools\Cursor Workplace\07-hyperframe")
OUT = ROOT / "scripts" / "audio_assembly" / "male_sentence_times.json"

def norm(s):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s)

def main():
    tr = json.loads((ROOT / "transcript.json").read_text(encoding="utf-8"))
    segs = {s["id"]: [] for s in tr["segments"]}
    for sen in tr["sentences"]:
        segs[sen["seg"]].append(sen)

    model = WhisperModel("small", device="cpu", compute_type="int8")
    result, report = {}, []
    for sid in ["S0", "S1", "S2", "S3", "S4", "S5"]:
        wav = ROOT / "assets" / "audio" / "male" / f"{sid}.wav"
        segments, _ = model.transcribe(str(wav), language="zh",
                                       word_timestamps=True,
                                       initial_prompt="旁白解说，普通话。")
        words = []
        for seg in segments:
            for w in (seg.words or []):
                words.append((w.word, w.start, w.end))
        asr_chars, asr_times = [], []
        for w, s, e in words:
            for ch in w:
                asr_chars.append(ch)
                asr_times.append((s, e))
        asr = "".join(asr_chars)

        sents = segs[sid]
        target = "".join(norm(x["text"]) for x in sents)
        spans, pos = [], 0
        for x in sents:
            n = len(norm(x["text"]))
            spans.append((pos, pos + n))
            pos += n

        sm = difflib.SequenceMatcher(None, target, asr, autojunk=False)
        t2a = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    t2a[i1 + k] = j1 + k
            elif tag == "replace" and j2 > j1:
                for k in range(i2 - i1):
                    t2a[i1 + k] = j1 + min(k, j2 - j1 - 1)
        matched = len(t2a) / max(1, len(target))
        out = []
        for (i0, i1), sen in zip(spans, sents):
            idxs = [t2a[i] for i in range(i0, i1) if i in t2a]
            if idxs:
                st = asr_times[min(idxs)][0]
                en = asr_times[max(idxs)][1]
                out.append({"idx": sen["idx"], "start": round(st, 3), "end": round(en, 3)})
            else:
                out.append({"idx": sen["idx"], "start": None, "end": None})
        result[sid] = out
        report.append(f"{sid}: matched={matched:.1%} chars={len(target)} asr={len(asr_chars)}")

    # 回退：段内比例分配
    for sid, out in result.items():
        if any(x["start"] is None for x in out):
            sents = segs[sid]
            total_chars = sum(len(norm(x["text"])) for x in sents)
            known = [x["end"] for x in out if x["end"] is not None]
            if not known:
                continue
            dur = max(known)
            acc = 0.0
            for x, sen in zip(out, sents):
                if x["start"] is None:
                    n = len(norm(sen["text"]))
                    x["start"] = round(acc * dur / total_chars, 3)
                    x["end"] = round((acc + n) * dur / total_chars, 3)
                acc += len(norm(sen["text"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report))
    print("written:", OUT)

if __name__ == "__main__":
    main()
