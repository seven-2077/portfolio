# -*- coding: utf-8 -*-
"""bgm_demo.py - BGM candidate demo builder (2026-11-07)

Outputs output/bgm_demo/*.wav, each 40s: same narration stem (build_mix spec
-19.5dB mean, 0.5s gaps) under each candidate BGM (-6dB mean + tanh 0.7),
i.e. the real production listen after a BGM swap. Baseline cuts mix_full.wav.

Usage: python bgm_demo.py
"""
import pathlib
import sys
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_mix import load_audio, mean_db, write_wav, SR, NARR_TARGET_DB, db_gain

ROOT = pathlib.Path(r"c:\Users\Seven\DeskBox\AI Tools\Cursor Workplace\07-hyperframe")
OUT = ROOT / "output" / "bgm_demo"
DEMO_S = 40.0
N = int(DEMO_S * SR)

OUT.mkdir(parents=True, exist_ok=True)

# ---------- 1. narration stem (S0+S1, same gain/gap as build_mix) ----------
parts = []
for sid in ["S0", "S1"]:
    a = load_audio(ROOT / ("assets/audio/male/" + sid + ".wav"), channels=1)
    a = a * db_gain(mean_db(a), NARR_TARGET_DB)
    parts.append(a)
    parts.append(np.zeros(int(0.5 * SR), dtype=np.float32))
narr = np.concatenate(parts)[:N]
print("narr stem: %.1fs mean=%.1fdB" % (len(narr) / SR, mean_db(narr)))

# ---------- 2. baseline: first 40s of current mix ----------
mix = load_audio(ROOT / "assets/audio/mix_full.wav", channels=1, dur=DEMO_S)
write_wav(OUT / "0_current_memories_of_stone.wav", mix)
print("0_current_memories_of_stone %.1fdB" % mean_db(mix))

# ---------- 3. candidate demos ----------
# (name, bgm path, start offset s) offsets per BGM_SOURCES.md timecodes
CANDS = [
    ("1_within_our_nature", "assets/audio/bgm_cand_2.mp3", 30),
    ("2_hiraeth", "assets/audio/bgm_cand_3.mp3", 35),
    ("3_home_was_you", "assets/audio/bgm_full_home_was_you.mp3", 60),
]
for name, path, off in CANDS:
    b = load_audio(ROOT / path, channels=1, start=off, dur=DEMO_S)
    b = b * db_gain(mean_db(b), -6.0)
    thr = 0.7
    b = (thr * np.tanh(b / thr)).astype(np.float32)
    m = narr + b
    pk = float(np.max(np.abs(m)))
    if pk > 0.97:
        m = m * (0.97 / pk)
    write_wav(OUT / (name + ".wav"), m)
    print("%s: bgm=%.1fdB peak=%.3f" % (name, mean_db(b), pk))

print("done ->", OUT)
