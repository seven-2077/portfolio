// src/export/gltf.js —— .glb 导出 + config.json 下载
//
// 合同：
//   exportGLB(root, filename?)  → Promise<Blob>（二进制 glb，触发浏览器下载）
//   exportJSON(data, filename?) → Blob（缩进 JSON，触发浏览器下载）
//
// pivot 规范（body.js 已保证）使 glb 在 Blender 中可直接复用拆解动画；
// config.json 与 localStorage 同 schema（serializeConfig 输出）。

import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** 把场景子树导出为 .glb 并下载；resolve Blob 便于测试/复用 */
export function exportGLB(root, filename = "electric-lotus.glb") {
  const exporter = new GLTFExporter();
  return new Promise((resolve, reject) => {
    exporter.parse(
      root,
      (result) => {
        const blob = new Blob([result], { type: "model/gltf-binary" });
        downloadBlob(blob, filename);
        resolve(blob);
      },
      (err) => reject(err),
      { binary: true, onlyVisible: false },
    );
  });
}

/** 配置对象 → .json 下载（与 panel.exportConfigJson 同 schema） */
export function exportJSON(data, filename = "electric-lotus-config.json") {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  downloadBlob(blob, filename);
  return blob;
}
