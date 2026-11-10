---
workflow: general-video
flow: automation
storyboard: no
message: "简单规则，能长出世间一切复杂之美"
destination: local playback
aspect: 16:9
language: zh
audience: Seven（个人欣赏）
length: 60s
angle: 科学视觉诗 —— 用今日六个科学项目的真实渲染产物，串成一部无人解说短片
---

## Intent

《涌现 Emergence》。黑屏起句「一条规则，能走多远？」，随后六幕各展示一种简单规则生出的复杂之美：

1. Koch 分形 —— 重复（stroke 逐笔生长）
2. L-system 蕨类 —— 生长（同样的语法长出生命）
3. 生命游戏 glider —— 邻居（四个细胞邻居一个宇宙）
4. Gray-Scott 反应扩散 —— 扩散（两种物质长出豹纹）
5. 双摆混沌 —— 分岔（初始差 0.0001，命运分道扬镳）
6. Mandelbrot —— 迭代（无穷细节藏在一次迭代里）

收尾：今日视觉产物马赛克快闪 → 落版「涌现 Emergence · 简单规则，复杂之美」+ mono 落款。

全部视觉素材来自今日真实渲染产物（fractals / life-diffusion / double-pendulum 项目 output/）。无人解说、无音乐，节奏由场景切换与文字 stagger 驱动。

## Assets

| 素材 | 来源 |
|---|---|
| `koch_snowflake.svg` `fern.svg` `mandelbrot.bmp` `julia_atlas.bmp` | `02-projects/fun/fractals/output/` |
| `rd_spots.svg` `rd_stripes.svg` `rd_worms.svg` `life_glider_strip.svg` | `02-projects/fun/life-diffusion/output/` |
| `trajectory_compare.svg` `divergence_log.svg` | `02-projects/fun/double-pendulum/output/` |
| `classic_hero_640x360.bmp` | `02-projects/fun/raytracer/output/`（收尾马赛克） |
| `zodiac_2026-11-05.svg` | `02-projects/fun/solar-system/output/`（收尾马赛克） |

字体：Noto Sans SC（系统已装，auto-capture）· Noto Serif SC · Archivo Black（捆绑）· IBM Plex Mono（捆绑）。

## Customizations

- Palette：bg `#0a0e14` 深蓝黑 / fg `#e9edf5` 冷白 / accent 琥珀 `#ffb454`（刻意避开 cyan-neon 懒默认；中性色向暖偏）
- Type：Noto Sans SC（陈述）× Noto Serif SC（引语，register 切换）+ Archivo Black（英文大词）+ IBM Plex Mono（`rule 01 / REPEAT` 角标）
- 每幕结构：mono 角标 + 中文引语（衬线）+ 真实素材 + 2-5 个带 ambient 动画的背景装饰（hairline / ghost text / radial glow / grid）
- 尺度：headline 64-120px · body 28-42px · label 18-24px · decorative opacity 12-25%
- 黑底补偿：body weight 350、line-height +0.05、display tracking -0.03em

## Notes

- `general-video` workflow 技能因 `raw.githubusercontent.com` SSL 干扰不可安装；ghfast（raw 超时）、jsdelivr（SSL）、`skills add`（repo/manifest 均无该技能）三条路均不通。按 route 契约（design → plan → layout → animation → check → render）使用本地已装 hyperframes-core / -creative / -cli 技能等效执行。
- `flow: automation` + `storyboard: no` 由用户信号锁定（"你来定，我就想看看效果和你的审美"）。
- 记忆探测：prefs `{}`、recipes `[]`（全新运行，无既往偏好）。
