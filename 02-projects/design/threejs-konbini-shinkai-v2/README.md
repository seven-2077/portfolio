# 日曜コンビニ · Shinkai v2

新海诚气质街角便利店。本目录为推倒重做版；旧版 `threejs-konbini-nichiyou` 仅对照，勿删。

## M1 静帧（当前）

**一栋**便利店为主体，外围是草坡、樱花树、铁道与通勤列车，以及电线 / 路灯等日常诗意元素——不再围一圈邻店街区。天空 / 大气、湿沥青 Reflector 倒影、立面·招牌·橱窗·雨棚、灯光分层。默认**雨黄昏**（`timeOfDay = 0.735`, `weather = rain`）。

交互（门 / 商品 / HUD / Audio / glTF）在静帧过审后再接，尚未开始。

## 预览

```
cd "C:\Users\Seven\DeskBox\AI Tools\Grok Bot Repriority\threejs-konbini-shinkai-v2\02-scene"
npm i
npm run dev
```

浏览器打开终端地址（默认 `http://localhost:5174`）。左键拖拽观察，滚轮推拉。截一帧审审美即可。

## Box 工作副本（尚未写入用户电脑）

当前可运行树在云电脑：`/workspace/threejs-konbini-shinkai-v2`。
**尚未同步**到 `C:\Users\Seven\DeskBox\AI Tools\Grok Bot Repriority\threejs-konbini-shinkai-v2`。

在 box 上预览：

```
cd /workspace/threejs-konbini-shinkai-v2/02-scene
npm i
npm run dev
```

默认 `http://localhost:5174`。改组后的内部检查帧：`01-refs/m1-rain-dusk-box.png`（无头 Chrome 截取，仅作构建验证，不是审美过审）。应用前备份：`/workspace/threejs-konbini-shinkai-v2.pre-env.bak`。
