# -*- coding: utf-8 -*-
"""数据图表生成 —— 甘肃脱贫与生态建设影像短片（HyperFrames 静态素材）。

一条命令重跑全部图表：

    python tools/charts.py

输出：assets/charts/*.png（2 倍分辨率，深色纪实风格）
数据与出处：assets/SOURCES.md 第三节「数据图表素材」
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D

# ----------------------------------------------------------------------------
# 路径与分辨率
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "charts"

BASE_W, BASE_H = 19.2, 10.8   # 英寸，@100dpi = 1920x1080（1080p 视觉比例）
SCALE = 2                       # 2 倍分辨率 → dpi=200 → 3840x2160
DPI = 100 * SCALE

# ----------------------------------------------------------------------------
# 风格常量（纪实政论片调性：深底、金/土黄/暖白，拒绝霓虹科技感）
# ----------------------------------------------------------------------------
BG = "#0d1117"      # 近黑深底
GOLD = "#ffb454"    # 金（强调、数据主体）
EARTH = "#a87c35"   # 土黄（柱体，沉稳）
INK = "#e9edf5"     # 暖白（正文）
MUTED = "#8b949e"   # 灰（来源、辅助说明）
GRID = "#ffffff"     # 网格用白 + 低透明度

FONT_CANDIDATES = ["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"]


def pick_cjk_font() -> str:
    """选一个系统里真实可用的中文字体，找不到就报错（宁可失败不出方块）。"""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            return name
    raise RuntimeError(
        "未找到可用中文字体，请确认系统安装了 Microsoft YaHei / SimHei"
    )


FONT = pick_cjk_font()

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [FONT],
    "axes.unicode_minus": False,
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": INK,
    "svg.fonttype": "none",
})

# 出处（英文写入 PNG 元数据，tEXt 只支持 Latin-1）
META_SOFTWARE = "matplotlib + 07-hyperframe/tools/charts.py"


def save(fig: plt.Figure, filename: str, title: str, source: str) -> Path:
    """保存 PNG（含来源元数据）并返回路径。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / filename
    fig.savefig(
        path,
        dpi=DPI,
        metadata={
            "Title": title,
            "Software": META_SOFTWARE,
            "Description": source,
            "Source": source,
        },
    )
    plt.close(fig)
    print(f"[ok] {path}")
    return path


def gold_rule(fig: plt.Figure, x: float, y: float, width: float = 0.06) -> None:
    """标题下方一小段金色短线（三图统一的克制装饰）。"""
    fig.add_artist(
        Line2D([x, x + width], [y, y], color=GOLD, lw=4.5,
               transform=fig.transFigure, solid_capstyle="butt")
    )


def footer(fig: plt.Figure, text: str, y: float = 0.045, x: float = 0.07) -> None:
    """底部来源行。"""
    fig.text(x, y, text, fontsize=17, color=MUTED, ha="left", va="center")


# ----------------------------------------------------------------------------
# 图 1：主图 —— 脱贫地区农村居民人均可支配收入（2020 / 2023 / 2024）
# ----------------------------------------------------------------------------
def chart_income() -> Path:
    years = ["2020", "2023", "2024"]
    values = [9385, 12107, 13015]

    fig, ax = plt.subplots(figsize=(BASE_W, BASE_H))
    fig.subplots_adjust(left=0.075, right=0.955, top=0.80, bottom=0.135)

    x = list(range(len(years)))

    # 柱体（土黄、克制）+ 折线（金、趋势）
    ax.bar(x, values, width=0.44, color=EARTH, zorder=3)
    ax.plot(x, values, color=GOLD, lw=4.5, zorder=4,
            marker="o", markersize=17, markerfacecolor=GOLD,
            markeredgecolor=BG, markeredgewidth=3.5)

    # 数值标签（大字号，视频里要看得清）
    for i, v in enumerate(values):
        ax.text(i, v + 430, f"{v:,}", ha="center", va="bottom",
                fontsize=36, color=INK, fontweight="bold", zorder=5,
                bbox=dict(facecolor=BG, edgecolor="none", pad=4))

    # 右上角增长注释
    ax.text(2.5, 16900, "2020 → 2024", ha="right", va="center",
            fontsize=25, color=MUTED, zorder=5)
    ax.text(2.5, 15400, "增长 38.7%", ha="right", va="center",
            fontsize=42, color=GOLD, fontweight="bold", zorder=5,
            bbox=dict(facecolor=BG, edgecolor="none", pad=6))

    # 坐标轴：留白、无多余边框
    ax.set_xlim(-0.6, 2.6)
    ax.set_ylim(0, 17800)
    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=28, color=INK)
    ax.set_yticks([0, 3000, 6000, 9000, 12000, 15000])
    ax.set_yticklabels([f"{t:,}" for t in
                        [0, 3000, 6000, 9000, 12000, 15000]],
                       fontsize=21, color=MUTED)
    ax.tick_params(axis="both", length=0, pad=12)
    ax.grid(axis="y", color=GRID, alpha=0.07, lw=1.2, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.spines["bottom"].set_alpha(0.25)

    # 标题区
    fig.text(0.075, 0.905, "甘肃脱贫地区农村居民人均可支配收入",
             fontsize=44, color=INK, ha="left", va="center")
    gold_rule(fig, 0.075, 0.868)
    fig.text(0.075, 0.838, "单位：元　·　2020—2024 年",
             fontsize=23, color=MUTED, ha="left", va="center")

    footer(fig, "数据来源：《2020 年甘肃省国民经济和社会发展统计公报》；"
                "国新办新闻发布会（2023 年）；甘肃省人大新闻发布会（2024 年）")

    return save(
        fig,
        "income_main.png",
        "Gansu poverty-area rural per capita disposable income 2020-2024",
        "Data sources: 2020 Gansu statistical bulletin; State Council "
        "Information Office press briefing (2023); Gansu People's Congress "
        "press conference (2024). See assets/SOURCES.md section 3.",
    )


# ----------------------------------------------------------------------------
# 图 2：引洮工程 —— 环形占比（约 1/4 人口）+ 右侧关键指标
# ----------------------------------------------------------------------------
def chart_yintao() -> Path:
    fig = plt.figure(figsize=(BASE_W, BASE_H))

    # 标题区
    fig.text(0.07, 0.905, "引洮工程", fontsize=44, color=INK,
             ha="left", va="center")
    gold_rule(fig, 0.07, 0.868)
    fig.text(0.07, 0.838, "一泓洮水润陇中　·　覆盖 5 市 13 县，600 多万人受益",
             fontsize=23, color=MUTED, ha="left", va="center")

    # 左侧环形图：受益人口约占全省 1/4
    ax = fig.add_axes([0.055, 0.15, 0.36, 0.60])
    ax.pie(
        [1, 3],
        colors=[GOLD, "#262d38"],
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.30, edgecolor=BG, linewidth=4),
    )
    ax.text(0, 0.14, "约 1/4", fontsize=66, color=GOLD,
            ha="center", va="center", fontweight="bold")
    ax.text(0, -0.24, "受益人口占全省比例", fontsize=24, color=INK,
            ha="center", va="center")
    ax.set_aspect("equal")

    # 右侧三行关键指标
    rows = [
        ("5 市 13 县", "工程覆盖范围"),
        ("600 多万人", "沿线受益人口"),
        ("5.75 亿立方米", "一期累计供水"),
    ]
    ys = [0.665, 0.455, 0.245]
    for (num, label), y in zip(rows, ys):
        fig.add_artist(Line2D(
            [0.50, 0.94], [y + 0.105, y + 0.105],
            color=GRID, alpha=0.10, lw=1.2, transform=fig.transFigure,
        ))
        fig.text(0.50, y, num, fontsize=54, color=GOLD,
                 ha="left", va="center", fontweight="bold")
        fig.text(0.50, y - 0.088, label, fontsize=24, color=MUTED,
                 ha="left", va="center")

    footer(fig, "数据来源：新华网《碧波奔流黄土坡——“引洮工程”的世纪圆梦故事》"
                "（2021 年 9 月）", x=0.07)

    return save(
        fig,
        "yintao_donut.png",
        "Yintao Project: population served is about 1/4 of Gansu",
        "Data source: Xinhua News, 'The Yintao Project' feature "
        "(Sep 2021): 5 cities 13 counties, 6+ million people served "
        "(about 1/4 of provincial population), 575 million m3 supplied "
        "in phase I. See assets/SOURCES.md section 3.",
    )


# ----------------------------------------------------------------------------
# 图 3：角标数字卡 —— 四个关键数字（宽幅条，适合放下三分之一）
# ----------------------------------------------------------------------------
def chart_numbers() -> Path:
    height = 6.4  # 19.2 x 6.4 英寸 → 基准 1920x640，2 倍 3840x1280
    fig = plt.figure(figsize=(BASE_W, height))

    fig.text(0.5, 0.87, "甘肃脱贫攻坚 · 关键数字",
             fontsize=26, color=MUTED, ha="center", va="center")

    cells = [
        ("75 个", ["贫困县全部摘帽"]),
        ("552 万人", ["建档立卡贫困人口", "全部脱贫"]),
        ("49.9 万人", ["易地扶贫搬迁"]),
        ("21.7 万亩", ["八步沙累计治沙造林"]),
    ]
    centers = [0.125, 0.375, 0.625, 0.875]

    for cx, (num, labels) in zip(centers, cells):
        fig.text(cx, 0.56, num, fontsize=58, color=GOLD,
                 ha="center", va="center", fontweight="bold")
        y = 0.335
        for line in labels:
            fig.text(cx, y, line, fontsize=25, color=INK,
                     ha="center", va="center")
            y -= 0.135

    # 格间细分隔线
    for sx in (0.25, 0.50, 0.75):
        fig.add_artist(Line2D(
            [sx, sx], [0.16, 0.72], color=GRID, alpha=0.14, lw=1.4,
            transform=fig.transFigure,
        ))

    footer(fig, "数据来源：2023 年甘肃省政府工作报告；"
                "央视《习近平甘肃行｜看八步沙林场新面貌》",
           y=0.05, x=0.5)
    # 来源行居中
    fig.texts[-1].set_ha("center")

    return save(
        fig,
        "key_numbers.png",
        "Gansu poverty alleviation key figures",
        "Data sources: 2023 Gansu government work report (75 counties "
        "removed from poverty list, 5.52 million people lifted out of "
        "poverty, 499,000 relocated); CCTV report on Babusha forest farm "
        "(217,000 mu of desert controlled). See assets/SOURCES.md section 3.",
    )


def main() -> None:
    print(f"中文字体：{FONT}（dpi={DPI}）")
    chart_income()
    chart_yintao()
    chart_numbers()
    print("全部完成。")


if __name__ == "__main__":
    main()
