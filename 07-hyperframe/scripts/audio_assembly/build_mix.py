# -*- coding: utf-8 -*-
"""build_mix.py — 音频总装主脚本（2026-11-07）

产出:
  assets/audio/mix_full.wav      全片唯一整轨（旁白+BGM包络+访谈原声）
  transcript.json                重算时间戳（文本字段不动）
  scripts/audio_assembly/timeline_v2.json   时间轴圣经（下游视觉任务消费）

规则来源: assets/video/AUDIO_ANALYSIS.md 第三节 + README 第七节任务书
"""
import json, subprocess, pathlib, numpy as np, datetime, sys

FF = r"C:\Users\Seven\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
FP = FF.replace("ffmpeg.exe", "ffprobe.exe")
ROOT = pathlib.Path(r"c:\Users\Seven\DeskBox\AI Tools\Cursor Workplace\07-hyperframe")
SR = 48000
INTER_SEG_GAP = 0.5
TAIL_S = 8.0   # 片尾演职员卡尾段（旁白结束后的静默+BGM环绕，312.06→320.06）

# 两个让位拍（旁白静音、片段原声全音量）
BEATS = [
    dict(id="beat_xincun", seg="S2", before_idx=16, dur=12.0,
         src="assets/video/xinhua_2024_dingxi_xincun.mp4", win=(0.0, 12.0),
         af="highpass=f=120,afftdn=nr=35:nf=-30",  # 源底噪-31 轻档，避免啃人声
         label="种植户访谈原声（承包千亩/马铃薯2500吨）"),
    dict(id="beat_babusha", seg="S3", before_idx=11, dur=15.0,
         src="assets/video/xinhua_2023_babusha_p1.mp4", win=(4.98, 19.98),
         af="highpass=f=120,afftdn=nr=70:nf=-21",  # 源底噪-22 信噪比~0dB 强档
         label="八步沙现场讲话原声（生态保护/新时代的愚公/向你们学）"),
]

# BGM 电平目标（dB，相对 BGM 自身 mean -16.3dB）
BGM_NARR_DB = -17.7   # 旁白期间 → 目标约 -34dB
BGM_BEAT_DB = -27.7   # 让位拍期间 → 目标约 -44dB
RAMP_S = 0.6          # 电平切换的线性斜坡
IV_TARGET_DB = -17.0  # 访谈原声目标 mean
NARR_TARGET_DB = -19.5  # 旁白目标 mean（v2.1 按用户反馈下调 1dB）

# 访谈降噪链（v2.1：p1 源信噪比仅 ~0dB，间隙底噪 -22dB，必须先降噪再归一）
INTERVIEW_AF = "highpass=f=120,afftdn=nr=70:nf=-21"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        print(p.stderr.decode("utf-8", "ignore")[-2000:])
        raise SystemExit(f"cmd failed: {' '.join(cmd[:6])}")
    return p


def load_audio(path, channels=1, start=None, dur=None, af=None):
    """ffmpeg 解码为 float32 numpy 数组（48k）"""
    cmd = [FF, "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    if af:
        cmd += ["-af", af]
    cmd += ["-ar", str(SR), "-ac", str(channels), "-f", "f32le", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"decode failed: {path}\n{p.stderr.decode('utf-8','ignore')[-800:]}")
    a = np.frombuffer(p.stdout, dtype=np.float32)
    if channels > 1:
        a = a.reshape(-1, channels)
    return a


def mean_db(x):
    r = np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12
    return 20 * np.log10(r)


def db_gain(from_db, to_db):
    return 10 ** ((to_db - from_db) / 20.0)


def write_wav(path, data, channels=2):
    if data.ndim == 1:
        data = np.repeat(data[:, None], channels, axis=1)
    cmd = [FF, "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", str(channels),
           "-i", "-", str(path)]
    p = subprocess.run(cmd, input=data.astype(np.float32).tobytes(), capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"write failed: {p.stderr.decode('utf-8','ignore')[-800:]}")


def main():
    tr = json.loads((ROOT / "transcript.json").read_text(encoding="utf-8"))
    stm = json.loads((ROOT / "scripts/audio_assembly/male_sentence_times.json").read_text(encoding="utf-8"))

    # ---------- 1. 每段切点与男声时长 ----------
    seg_meta = {}
    for s in tr["segments"]:
        sid = s["id"]
        wav = ROOT / "assets/audio/male" / f"{sid}.wav"
        wdur = float(run([FP, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(wav)]).stdout.strip())
        sent = stm[sid]
        split_at = None
        beat = next((b for b in BEATS if b["seg"] == sid), None)
        if beat:
            prev_end = [x for x in sent if x["idx"] == beat["before_idx"] - 1][0]["end"]
            nxt_start = [x for x in sent if x["idx"] == beat["before_idx"]][0]["start"]
            split_at = (prev_end + nxt_start) / 2.0
        seg_meta[sid] = dict(wdur=wdur, split=split_at, beat=beat, sent=sent)

    # ---------- 2. 拼旁白轨（含段间 0.5s 与拍内静音） ----------
    narr_parts, t = [], 0.0
    seg_bounds, sent_abs, beat_abs = {}, [], []
    for s in tr["segments"]:
        sid = s["id"]
        m = seg_meta[sid]
        wav = ROOT / "assets/audio/male" / f"{sid}.wav"
        a = load_audio(wav, channels=1)
        g = db_gain(mean_db(a), NARR_TARGET_DB)
        a = a * g
        seg_start = t
        if m["split"] is not None:
            b = m["beat"]
            cut = int(round(m["split"] * SR))
            narr_parts.append(a[:cut])
            narr_parts.append(np.zeros(int(b["dur"] * SR), dtype=np.float32))
            b_abs = (seg_start + m["split"], seg_start + m["split"] + b["dur"])
            beat_abs.append(dict(id=b["id"], start_s=round(b_abs[0], 3), end_s=round(b_abs[1], 3),
                                 source=b["src"], source_window=f'{b["win"][0]}-{b["win"][1]}s',
                                 label=b["label"]))
            narr_parts.append(a[cut:])
            seg_dur = m["wdur"] + b["dur"]
        else:
            narr_parts.append(a)
            seg_dur = m["wdur"]
        seg_end = seg_start + seg_dur
        seg_bounds[sid] = (seg_start, seg_end, m["wdur"], m["split"], m["beat"] and m["beat"]["dur"] or 0.0)
        # 句绝对时间
        for x in m["sent"]:
            off = x["start"]
            if m["split"] is not None and x["start"] >= m["split"]:
                off += m["beat"]["dur"]
            sent_abs.append(dict(seg=sid, idx=x["idx"],
                                 start_s=round(seg_start + off, 3),
                                 end_s=round(seg_start + off + (x["end"] - x["start"]), 3)))
        t = seg_end + INTER_SEG_GAP
        if s is not tr["segments"][-1]:
            narr_parts.append(np.zeros(int(INTER_SEG_GAP * SR), dtype=np.float32))
    film_end = t - INTER_SEG_GAP  # 最后一段后无间隙
    narr = np.concatenate(narr_parts)
    assert abs(len(narr) / SR - film_end) < 0.05, (len(narr) / SR, film_end)
    # 片尾卡尾段：旁白后补静音，BGM 环绕至 audio_total 才淡出
    audio_total = film_end + TAIL_S
    narr = np.concatenate([narr, np.zeros(int(TAIL_S * SR), dtype=np.float32)])

    # ---------- 3. 访谈原声提取 ----------
    iv = np.zeros(int(np.ceil(audio_total) * SR) + SR, dtype=np.float32)
    for b in beat_abs:
        src = [x for x in BEATS if x["id"] == b["id"]][0]
        clip = load_audio(ROOT / src["src"], channels=1,
                          start=src["win"][0], dur=src["win"][1] - src["win"][0],
                          af=src.get("af") or INTERVIEW_AF)
        n = min(len(clip), int(round((b["end_s"] - b["start_s"]) * SR)))
        clip = clip[:n] * db_gain(mean_db(clip[:n]), IV_TARGET_DB)
        # 50ms 边缘淡入淡出
        f = int(0.05 * SR)
        clip[:f] *= np.linspace(0, 1, f, dtype=np.float32)
        clip[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
        st = int(round(b["start_s"] * SR))
        iv[st:st + n] += clip

    # ---------- 4. BGM 包络 ----------
    bgm = load_audio(ROOT / "assets/audio/bgm_full_memories_of_stone.mp3", channels=2)
    need = int(np.ceil(audio_total) * SR)
    if len(bgm) < need:  # 循环补齐
        reps = int(np.ceil(need / len(bgm)))
        bgm = np.tile(bgm, (reps, 1))
    bgm = bgm[:need]
    bgm_src_db = mean_db(bgm)
    gain_n, gain_b = db_gain(bgm_src_db, BGM_NARR_DB + 0), db_gain(bgm_src_db, BGM_BEAT_DB + 0)
    # 注：BGM_NARR_DB/BGM_BEAT_DB 已按绝对目标写（-34/-44 = -16.3-17.7 ...），这里直接换算
    gain_n = 10 ** ((-11.0 - bgm_src_db) / 20)  # v3.4: -6 → -11（2026-11-07 用户要求整体再降5dB）
    gain_b = 10 ** ((-22.0 - bgm_src_db) / 20)  # v3.4: -17 → -22（同步降5dB）

    n_samp = len(bgm)
    env = np.full(n_samp, gain_n, dtype=np.float32)
    ramp = int(RAMP_S * SR)
    for b in beat_abs:
        i0 = int(round(b["start_s"] * SR))
        i1 = int(round(b["end_s"] * SR))
        env[i0:i1] = gain_b
        # 斜坡：进拍前 0.6s 从 narr→beat，出拍后 0.6s beat→narr
        for (a_, b_, rising) in [(max(0, i0 - ramp), i0, True), (i1, min(n_samp, i1 + ramp), False)]:
            if b_ <= a_:
                continue
            seg = np.linspace(0, 1, b_ - a_, dtype=np.float32)
            if not rising:
                seg = seg[::-1]
            env[a_:b_] = gain_b + (gain_n - gain_b) * (seg if rising else seg)
            # rising: gain_n→gain_b? 修：进拍应从 gain_n 降到 gain_b
    # 上面斜坡方向写反了，重写包络斜坡（简单可靠版）
    env = np.full(n_samp, gain_n, dtype=np.float32)
    for b in beat_abs:
        i0 = int(round(b["start_s"] * SR)); i1 = int(round(b["end_s"] * SR))
        env[i0:i1] = gain_b
        a0, a1 = max(0, i0 - ramp), i0
        if a1 > a0:
            k = np.linspace(0, 1, a1 - a0, dtype=np.float32)
            env[a0:a1] = gain_n + (gain_b - gain_n) * k   # narr→beat
        b0, b1 = i1, min(n_samp, i1 + ramp)
        if b1 > b0:
            k = np.linspace(0, 1, b1 - b0, dtype=np.float32)
            env[b0:b1] = gain_b + (gain_n - gain_b) * k   # beat→narr
    # 片头前奏段抬升：源曲 0-57s 排列稀疏（6s 脉冲、间隙深），叠开头解说下听不到
    # 额外 +2dB，57-65s 斜坡平滑回落（配合全局 +5dB 共同解决）
    intro_lift = 10 ** (2.0 / 20)
    i_end, i_ramp = int(57 * SR), int(65 * SR)
    env[:i_end] *= intro_lift
    k = np.linspace(1.0, 0.0, i_ramp - i_end, dtype=np.float32)
    env[i_end:i_ramp] *= 1.0 + (intro_lift - 1.0) * k
    # 片尾 2s BGM 淡出
    fade = int(2.0 * SR)
    env[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    bgm = bgm * env[:, None]
    # 峰值软限幅（激进档）：均值抬到 -6dB 后峰值会到 +9dB，
    # 用 tanh 把峰值压回 ≈-3dB，防止撑爆总线触发整体缩放把人声压暗
    thr = 0.7
    bgm = thr * np.tanh(bgm / thr)

    # ---------- 5. 合轨 ----------
    bgm_m = bgm.mean(axis=1) if bgm.ndim == 2 else bgm
    n = min(len(narr), len(bgm_m), len(iv))
    mix = narr[:n] + bgm_m[:n] + iv[:n]
    peak = float(np.max(np.abs(mix)))
    if peak > 0.97:
        mix = mix * (0.97 / peak)
    mix_st = np.repeat(mix[:, None], 2, axis=1)
    out_wav = ROOT / "assets/audio/mix_full.wav"
    write_wav(out_wav, mix_st, channels=2)

    # ---------- 6. transcript.json 重算 ----------
    tr["generated_at"] = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    tr["version"] = 2
    tr["total_duration_s"] = round(audio_total, 3)
    tr["narration_end_s"] = round(film_end, 3)
    tr["gap_between_segments_s"] = INTER_SEG_GAP
    tr["narration_voice"] = "mimo-v2.5-tts-voiceclone / 钟离(CV彭博) / assets/audio/male/"
    tr["audio_mix"] = "assets/audio/mix_full.wav"
    tr["beats"] = beat_abs
    for s in tr["segments"]:
        st, en, wdur, split, bdur = seg_bounds[s["id"]]
        s["start_s"] = round(st, 3); s["end_s"] = round(en, 3)
        s["duration_s"] = round(en - st, 3)
        s["narration_audio_s"] = round(wdur, 3)
        s["audio"] = f"assets/audio/male/{s['id']}.wav"
        if bdur:
            s["internal_beat_s"] = round(bdur, 3)
    for x in tr["sentences"]:
        src = [y for y in sent_abs if y["seg"] == x["seg"] and y["idx"] == x["idx"]][0]
        x["start_s"] = src["start_s"]; x["end_s"] = src["end_s"]
    (ROOT / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 7. timeline_v2.json ----------
    tl = dict(
        version=1, generated_at=tr["generated_at"],
        total_duration_s=round(audio_total, 3),
        film_end_s=round(audio_total, 3),
        narration_end_s=round(film_end, 3),
        audio_mix="assets/audio/mix_full.wav",
        beats=beat_abs,
        segments=[dict(id=s["id"], start_s=round(seg_bounds[s["id"]][0], 3),
                       end_s=round(seg_bounds[s["id"]][1], 3),
                       narration_audio_s=round(seg_bounds[s["id"]][2], 3))
                  for s in tr["segments"]],
        sentences=sent_abs,
        rules=dict(inter_segment_gap_s=INTER_SEG_GAP,
                   tail_card_s=TAIL_S,
                   bgm="Memories Of Stone 全片垫底: 旁白段-6dB / 让位拍-17dB / 片头0-57s+2dB / tanh软限幅-3dB / 片尾2s淡出（含8s片尾卡尾段）",
                   narration_target_mean_db=NARR_TARGET_DB,
                   interview_target_mean_db=IV_TARGET_DB,
                   clip_policy="除让位拍外全部素材音轨静音（AUDIO_ANALYSIS.md 第三节）"),
    )
    (ROOT / "scripts/audio_assembly/timeline_v2.json").write_text(
        json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"film_end={film_end:.3f}s  audio_total={audio_total:.3f}s  ({int(audio_total//60)}:{audio_total%60:05.2f})")
    print("beats:", [(b['id'], b['start_s'], b['end_s']) for b in beat_abs])
    print("segments:", {k: (round(v[0],2), round(v[1],2)) for k, v in seg_bounds.items()})
    print("peak:", round(peak, 3), " mix mean dB:", round(float(mean_db(mix)), 1))
    print("written: mix_full.wav / transcript.json / timeline_v2.json")


if __name__ == "__main__":
    main()
