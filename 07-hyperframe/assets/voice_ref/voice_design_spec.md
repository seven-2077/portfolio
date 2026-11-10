# Voice Design 旁白男声音色规格（可复现）

voice design 路线：不依赖参考音频，用文字描述让模型现场设计音色。
本文件记录最终采用的完整调用参数，后续重合成全片 6 段旁白（S0–S5）必须照此复现。

## 模型与端点

- 模型：`mimo-v2.5-tts-voicedesign`（Token Plan `/v1/models` 列表确认存在）
- 端点：`https://token-plan-cn.xiaomimimo.com/v1/chat/completions`（POST）
- 鉴权：请求头 `api-key: <MIMO_API_KEY>`（与 `tools/tts_synthesize.py` 同源，读环境变量或项目根 `.env`）

## 调用格式

voice design 路线**不传** `audio.voice`，音色描述放在 user 消息里：

```json
{
  "model": "mimo-v2.5-tts-voicedesign",
  "messages": [
    {"role": "user",      "content": "<voice description>。<style>"},
    {"role": "assistant", "content": "<要合成的旁白文本>"}
  ],
  "audio": {"format": "wav"}
}
```

响应：`choices[0].message.audio.data` 为 base64 WAV（24 kHz / 16 bit / 单声道）。

## 最终采用的音色描述（voice description）

```
成年男声，低沉厚重，胸腔共鸣强烈，中低频饱满有磁性，纪录片旁白解说气质，语速沉稳偏慢，咬字字正腔圆，吐字干净，情绪克制庄重，无口音
```

（对应试音文件 `assets/audio/male_design_2.wav`，26.24 s / 86 字 ≈ 197 字/分，为选定版）

## Style（语气风格指令，追加在描述之后，用「。」连接）

```
沉稳庄重的纪录片旁白，男声，语速平缓，叙事感强，情绪克制而有力量，字正腔圆
```

（与 `tools/tts_synthesize.py` 的 `DEFAULT_STYLE` 一致，也与 male_test_1/2 克隆候选同 style，保证三方背靠背可比）

## 备选版（更沉更闷，未采用）

- voice description：`中年男声，低沉厚重，胸腔共鸣强烈，音色偏闷带颗粒感，纪录片旁白解说气质，语速沉稳偏慢，咬字字正腔圆，情绪克制庄重，无口音`
- 试音文件：`assets/audio/male_design_1.wav`（27.68 s / 86 字 ≈ 186 字/分）

## 合成命令（复现全片用）

```powershell
# 单段（脚本 --design 自动选中 mimo-v2.5-tts-voicedesign）
python tools/tts_synthesize.py --only S0 --design "成年男声，低沉厚重，胸腔共鸣强烈，中低频饱满有磁性，纪录片旁白解说气质，语速沉稳偏慢，咬字字正腔圆，吐字干净，情绪克制庄重，无口音"
# URL 需设 MIMO_TTS_URL=https://token-plan-cn.xiaomimimo.com/v1/chat/completions
```

全片 6 段合成时，把上面「最终采用的 voice description + style」原样传入即可。
现 `assets/audio/S0.wav`–`S5.wav` 为旧女声版本，重合成前先确认已选定本音色。

## 验证记录（2026-11-06）

- `male_design_1.wav`：27.68 s，≈186 字/分，mean_volume −23.3 dB，max_volume −2.6 dB
- `male_design_2.wav`：26.24 s，≈197 字/分，mean_volume −22.6 dB，max_volume −1.0 dB

均满足 ffprobe 可解析、语速 180–220 字/分、响度均值 ≥ −35 dB。
