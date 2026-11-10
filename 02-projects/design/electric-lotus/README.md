# 电莲花 · electric-lotus

> three.js + GLSL + Canvas2D + WebAudio 的交互式跑车配置器
> 造型基准：莲花纯电超跑 —— Theory 1 楔形包裹车身 × Evija 孔隙风道

程序化建模的电莲花超跑：楔形硬朗折面、悬浮式车头、technology band 腰线、
文丘里风道、反向翼式车门。支持按机构逻辑的创意拆解（黄金角花瓣阵列落位）、
四参数喷漆、四套车展风格背景、配件自由搭配，一键导出 glTF 转 Blender。

---

## 快速启动

```powershell
cd 02-projects/design/electric-lotus
npm install            # 首次（node_modules 不入库）
python -m http.server 8031
# 浏览器打开 http://localhost:8031
```

> 必须走本地服务器：ES modules + import map 不允许 file:// 直开。

跑测试：

```powershell
node --test tests/
```

---

## 操作

（Phase 3 集成后补全：拆解/喷漆/背景/配件/导出的完整操作说明）

---

## 造型基准

- **主体轮廓 · Lotus Theory 1**：楔形 shrink-wrap 车身、悬浮式无格栅车头、
  纤细激光灯带、黑色 technology band、反向翼式车门、大尾翼+扩散器、三座椅中置
- **孔隙细节 · Lotus Evija**：文丘里风道贯穿侧身到车尾、不规则 LED 尾灯带
- **硬朗手段**：楔形折面为主、technology band 硬分割、锐利腰线、轮眉外扩

## Blender 接口

- 「导出 glb」按钮 → `output/electric-lotus.glb`（GLTFExporter）
- 部件命名规范：`body_petal_front` / `door_left` / `wheel_FL` / `wing_rear` /
  `battery_pack` / `seat_center`（pivot 在真实铰链/安装点）
- 配置状态同步导出 `config.json`（色值、选配件、背景）

## 项目结构

```
electric-lotus/
├── index.html            # import map + 启动自检
├── styles.css            # 车展风格 UI
├── src/
│   ├── main.js           # 接线层
│   ├── body.js           # 楔形车身参数化建模 + 部件 pivot
│   ├── scene.js          # 相机/预设机位/转盘/拾取
│   ├── backgrounds.js     # 4 背景灯光 rig
│   ├── explode.js         # 拆解编排（铰链轨迹 + 黄金角落位）
│   ├── hud.js             # Canvas2D 引线标注 + 仪表
│   ├── materials/paint.js # 车漆三层 GLSL
│   ├── ui/panel.js        # 配置面板状态
│   ├── audio/engine.js    # WebAudio 电机/音效
│   └── export/gltf.js     # glb + config.json 导出
├── tests/                # node --test 纯逻辑单测
├── assets/               # 静态资源
└── output/               # 导出产物（不入库）
```

MIT License
