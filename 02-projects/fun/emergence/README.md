# 涌现 · Emergence

> 一条规则，能走多远？—— 60 秒无人解说短片，全部画面来自本工作区六个科学项目的真实渲染产物。

用 HyperFrames（HTML → 视频）制作的单文件 composition：8 幕、60 秒、1920×1080 @30fps，一个 paused GSAP timeline 驱动。

## 分镜

| 幕 | 时间 | 规则 | 画面 |
|---|---|---|---|
| S0 | 0-6s | — | 黑屏起句「一条规则，能走多远？」 |
| S1 | 6-14s | repeat | Koch 雪花圆形绽放（fractals 项目） |
| S2 | 14-22s | grow | 蕨类自下而上生长（L-system） |
| S3 | 22-30s | neighbors | glider 条带横移（Conway B3/S23） |
| S4 | 30-38s | diffuse | 反应扩散三联：spots / stripes / worms |
| S5 | 38-46s | chaos | 双摆轨迹 + 分岔图，Δθ = 10⁻⁴ rad |
| S6 | 46-54s | iterate | Mandelbrot 缓慢推近 + Julia 角标 |
| S7 | 54-60s | — | 12 图马赛克快闪 → 落版「涌现 · 简单规则，复杂之美」 |

## 设计

- **Palette**：深蓝黑 `#0a0e14` / 冷白 `#e9edf5` / 琥珀 `#ffb454`（刻意避开 cyan-neon 懒默认）
- **字体**：Noto Sans SC（陈述）× Noto Serif SC（引语）+ Archivo Black（英文大词）+ IBM Plex Mono（角标）
- **素材**：`assets/` 内 12 张图全部复制自 `fractals` / `life-diffusion` / `double-pendulum` / `raytracer` / `solar-system` 的 `output/`
- **GSAP 与字体全部本地化**（`node_modules/`、`fonts/`），渲染零外网依赖

## 命令

```bash
npm run check      # lint + runtime + layout + motion + contrast 五项联审
npm run render -- --output renders/emergence.mp4 --quality looks
```

本机注意：Chrome for Testing 下载被网络干扰，需用系统 Edge：

```powershell
$env:HYPERFRAMES_BROWSER_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

## 环境记录

- `general-video` workflow 技能因 `raw.githubusercontent.com` SSL 干扰不可安装（ghfast / jsdelivr / skills add 三条 fallback 均不通），按 route 契约用本地 core/creative/cli 技能等效执行，详见 `BRIEF.md`。
- HyperFrames `0.9.15`（package.json 固定）。
