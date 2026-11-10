# -*- coding: utf-8 -*-
"""片尾演职员卡生成 —— ComfyUI MOSS-Image（MossMangaLayout JSON 排版）

环境备忘：
  ComfyUI:  D:\\Project Software\\ComfyUI-aki\\ComfyUI-aki-v3.2\\ComfyUI
  启动:     venv\\Scripts\\python.exe -s main.py --port 8188 --disable-auto-launch
            （工作目录为 ComfyUI 目录；python\\python.exe 已损坏，必须用 venv 的）
  API:      http://127.0.0.1:8188
  模型:     moss_image_sft_int8_convrot + qwen3.5_9b_w4a8_gptq + flux2-vae
  LoRA:     KOOK-MOSS-SFT-观澜 + MOSS-4步加速LoRA-v2.0（4 步 cfg1）

用法: python gen_ending_card.py [--seed 20261107]
"""
import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parents[2]          # 07-hyperframe
COMFY_OUTPUT = Path(r"D:\Project Software\ComfyUI-aki\ComfyUI-aki-v3.2\ComfyUI\output")
OUT_DIR = ROOT / "output" / "ending_card"
WF_DIR = ROOT / "assets" / "comfyui"

# ---------------------------------------------------------------- 版式快照
# 画布 1456x816（16:9 近似，适配片尾 1920x1080 画框），坐标为画布中心原点 [y0,x0,y1,x1]
SNAPSHOT = {
    "id": "ending_card_gansu",
    "label": "甘肃足迹·片尾演职员卡",
    "description": "深青黑夜色沙丘背景的片尾卡：金色敦煌风双线框与四角卷草纹，"
                   "中央自上而下金色彩色文字——片名、副题、装饰分隔、组长与组员名单。",
    "usage": "单格整页片尾卡。背景为夜色下的陇原大地：黄河如一条微光金色缎带蜿蜒于画面下部，"
             "远景山脊上有长城烽燧剪影，稀疏星尘；极简金色发丝线内框，四角短直角括线，框顶正中一枚小金星；"
             "文字为金色衬线体居中，自上而下：主片名、副题、细分隔线、组长行、组员行（名单字号小于片名）。"
             "框用途是内容分配说明，不作为图中文字。",
    "readingOrder": "F → C → T → SUB → DIV → N_1 → N_2",
    "canvas": {"width": 1456, "height": 816},
    "panels": [{
        "position": "card",
        "layer": 0,
        "slots": {
            "F":   [-404, -724, 404, 724],
            "C":   [-376, -692, 376, 692],
            "T":   [-270, -560, -120, 560],
            "SUB": [-110, -300,  -45, 300],
            "DIV": [ -15, -260,   45, 260],
            "N_1": [  95, -400,  159, 400],
            "N_2": [ 179, -460,  243, 460],
        },
        "slotNotes": {
            "F": "全页背景：深青黑到墨蓝的夜空渐变，画面下三分之一是清晰可辨的层叠高原与沙丘近黑剪影，"
                 "地平线泛着柔和青光；黄河作为一条明亮的金色发光缎带蜿蜒横贯画面下部，"
                 "右侧山脊上一座清晰的长城烽燧剪影衬着微亮天际，天空疏朗金色星尘，"
                 "上中部留安静夜空给文字，庄重有电影感。",
            "C": "极简边框：一条很细的金色发丝线矩形内框，四角各一枚略亮的短直角括线，"
                 "框顶正中一枚很小的金色五角星；无花纹、无重复装饰母题，干净素雅。",
            "T": "主片名，大号金色衬线中文字，居中排布，字形优雅庄重。",
            "SUB": "副题一行，小号金色中文字，字距拉开，居中。",
            "DIV": "细分隔线：一条细金线，正中一枚很小的菱形点。",
            "N_1": "名单第一行，小号金色衬线中文，居中，字号明显小于片名，克制内敛。",
            "N_2": "名单第二行，小号金色衬线中文，居中，字号与上一行一致，姓名之间用间隔号分开。",
        },
    }],
    "promptMode": "llm",
}

# ---------------------------------------------------------------- 布局提示词
LAYOUT_JSON = {
    "summary": {
        "caption": "A restrained documentary end-credits card themed on the Gansu landscape: "
                   "deep ink-teal night sky, the Yellow River winding as a softly glowing golden "
                   "ribbon across the lower third over near-black loess plateau and dune "
                   "silhouettes, a small distant Great Wall beacon tower on the right ridge, "
                   "sparse golden star dust, a minimal museum-style hairline golden frame with "
                   "short corner brackets and one tiny five-pointed star at the top center, "
                   "all text in refined golden serif Chinese type, centered and calm, "
                   "large empty dark space kept in the middle.",
        "palette": ["deep ink-teal night", "golden river glow", "near-black silhouettes",
                    "ivory-gold text"],
    },
    "items": [
        {"panel": 1, "slot": "F", "label": "object",
         "caption": "Full-page background: deep ink-teal to midnight-blue night gradient; "
                    "across the lower third, clearly visible layered loess plateau and dune "
                    "ridges in near-black silhouette against a soft teal horizon glow; the "
                    "Yellow River winds prominently across the scene as a glowing golden "
                    "ribbon of light; on the right ridge a clearly visible small silhouette "
                    "of a Great Wall beacon tower against the glowing horizon; sparse subtle "
                    "golden star dust in the sky; the upper center is quiet empty dark sky "
                    "for the text, solemn and cinematic, no people."},
        {"panel": 1, "slot": "C", "label": "object",
         "caption": "Minimal museum frame: one very thin golden hairline rectangle inset from "
                    "the edges, a short brighter right-angle bracket at each of the four "
                    "corners, one tiny golden five-pointed star centered on the top edge of the "
                    "frame; no floral patterns, no repeating motifs, clean and restrained."},
        {"panel": 1, "slot": "T", "label": "text",
         "caption": "Main film title, very large elegant golden Chinese serif lettering, "
                    "centered horizontally, single line.",
         "text": "足迹里的思政课"},
        {"panel": 1, "slot": "SUB", "label": "text",
         "caption": "Subtitle line, small golden Chinese lettering with wide letter spacing, "
                    "centered directly under the title.",
         "text": "甘肃足迹"},
        {"panel": 1, "slot": "DIV", "label": "object",
         "caption": "A single thin horizontal gold divider line with one tiny diamond accent "
                    "at its center.",
         },
        {"panel": 1, "slot": "N_1", "label": "text",
         "caption": "Credits line one, small golden Chinese serif lettering, centered, "
                    "clearly smaller than the film title, modest and understated.",
         "text": "组长：何谭昕"},
        {"panel": 1, "slot": "N_2", "label": "text",
         "caption": "Credits line two, small golden Chinese serif lettering, same size as the "
                    "line above, centered, names separated by middle dots.",
         "text": "组员：李安 · 梁日皓 · 唐子帆"},
    ],
}


def build_workflow(seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "moss_image_sft_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {
            "model": ["1", 0], "shift": 5, "sampling": "flow"}},
        "4": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3.5_9b_w4a8_gptq.safetensors", "type": "moss_image",
            "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "6": {"class_type": "MossMangaLayout", "inputs": {
            "layout_json": json.dumps(LAYOUT_JSON, ensure_ascii=False),
            "layout_id": SNAPSHOT["id"],
            "layout_snapshot": json.dumps(SNAPSHOT, ensure_ascii=False)}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": ["6", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {
            "clip": ["4", 0],
            "text": "lowres, bad anatomy, extra fingers, fused fingers, deformed hands, "
                    "extra limbs, blurry, jpeg artifacts, watermark, signature, cropped, "
                    "out of frame, worst quality, low quality, gibberish text, unreadable "
                    "text, misspelled text"}},
        "9": {"class_type": "EmptyFlux2LatentImage", "inputs": {
            "width": ["6", 1], "height": ["6", 2], "batch_size": 1}},
        "10": {"class_type": "KSampler", "inputs": {
            "model": ["13", 0], "positive": ["7", 0], "negative": ["8", 0],
            "latent_image": ["9", 0], "seed": seed, "steps": 4, "cfg": 1,
            "sampler_name": "euler", "scheduler": "sgm_uniform", "denoise": 1}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["5", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {
            "images": ["11", 0], "filename_prefix": "ending_card_gansu"}},
        "13": {"class_type": "LoadLoraModel", "inputs": {
            "model": ["2", 0],
            "loras.0.lora_name": "KOOK-MOSS-SFT-观澜.safetensors",
            "loras.0.strength": 1,
            "loras.0.enabled": True,
            "loras.1.lora_name": "【Moss】MOSS-4步加速LoRA-v2.0.safetensors",
            "loras.1.strength": 1,
            "loras.1.enabled": True}},
    }


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261107)
    args = ap.parse_args()

    try:
        urllib.request.urlopen(API + "/system_stats", timeout=5)
    except Exception:
        print("ComfyUI API 不在线，请先启动：")
        print(r'  cd "D:\Project Software\ComfyUI-aki\ComfyUI-aki-v3.2\ComfyUI"')
        print(r'  ..\venv\Scripts\python.exe -s main.py --port 8188 --disable-auto-launch')
        return 2

    wf = build_workflow(args.seed)
    WF_DIR.mkdir(parents=True, exist_ok=True)
    (WF_DIR / "ending_card_workflow.json").write_text(
        json.dumps({"prompt": wf}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"工作流已存: {WF_DIR / 'ending_card_workflow.json'}")

    try:
        resp = post_json(API + "/prompt", {"prompt": wf, "client_id": "ending-card-script"})
    except urllib.error.HTTPError as e:
        print("提交被拒 HTTP", e.code, ":")
        print(e.read().decode("utf-8", "replace")[:3000])
        return 1
    if "prompt_id" not in resp:
        print("提交失败:", json.dumps(resp, ensure_ascii=False)[:2000])
        return 1
    pid = resp["prompt_id"]
    print(f"已提交 prompt={pid}，等待生成...")

    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(f"{API}/history/{pid}", timeout=10) as r:
                hist = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        entry = hist.get(pid)
        if not entry:
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            print("生成出错:")
            for m in status.get("messages", []):
                if m[0] == "execution_error":
                    print(json.dumps(m[1], ensure_ascii=False, indent=2)[:3000])
            return 1
        outputs = entry.get("outputs", {})
        for node_out in outputs.values():
            for img in node_out.get("images", []):
                name = img["filename"]
                src = COMFY_OUTPUT / name
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                dst = OUT_DIR / name
                shutil.copy2(src, dst)
                print(f"完成: {dst}")
                return 0
        if status.get("completed"):
            print("任务完成但未找到图像输出:", json.dumps(outputs, ensure_ascii=False)[:1000])
            return 1
    print("等待超时（10 分钟）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
