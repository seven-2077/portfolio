import {
  AdditiveBlending,
  CanvasTexture,
  Color,
  DoubleSide,
  Group,
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  Vector3,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';

/**
 * Ground-hugging dusk mist that wraps the store and trees lightly
 * and thickens toward the railway, hills, and train.
 */
function mistTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 256;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  const grd = g.createRadialGradient(128, 128, 20, 128, 128, 128);
  grd.addColorStop(0, 'rgba(210,218,230,1)');
  grd.addColorStop(0.45, 'rgba(190,200,220,0.55)');
  grd.addColorStop(1, 'rgba(180,190,210,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 256, 256);
  const t = new CanvasTexture(c);
  t.needsUpdate = true;
  return t;
}

const vert = /* glsl */ `
varying vec2 vUv;
varying vec3 vWorldPos;
void main() {
  vUv = uv;
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorldPos = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const frag = /* glsl */ `
uniform sampler2D uMap;
uniform vec3 uColor;
uniform float uOpacity;
varying vec2 vUv;
varying vec3 vWorldPos;
void main() {
  float mask = texture2D(uMap, vUv).a;
  // Keep a lighter veil near the store, thicken with distance
  float dist = length(vWorldPos.xz);
  float nearFade = smoothstep(4.0, 14.0, dist);
  float a = mask * uOpacity * mix(0.35, 1.0, nearFade);
  a *= smoothstep(0.0, 0.12, vUv.x) * smoothstep(1.0, 0.88, vUv.x);
  a *= smoothstep(0.0, 0.12, vUv.y) * smoothstep(1.0, 0.88, vUv.y);
  if (a < 0.004) discard;
  gl_FragColor = vec4(uColor, a);
}
`;

export class Mist {
  readonly group = new Group();
  private mats: ShaderMaterial[] = [];
  private tex: CanvasTexture;

  constructor() {
    this.group.name = 'mist';
    this.tex = mistTexture();

    const layers: Array<{ pos: Vector3; w: number; d: number; yRot?: number; opacity: number }> = [
      // wraps the store and left sakura, very thin
      { pos: new Vector3(-4, 1.15, 2.5), w: 22, d: 16, opacity: 0.07 },
      // mid field behind the store
      { pos: new Vector3(2, 1.6, -14), w: 40, d: 22, opacity: 0.11 },
      // railway / train belt
      { pos: new Vector3(16, 2.2, -44), w: 70, d: 18, opacity: 0.16 },
      // hills
      { pos: new Vector3(0, 4.5, -80), w: 160, d: 40, opacity: 0.18 },
      { pos: new Vector3(0, 8.0, -120), w: 200, d: 50, opacity: 0.14 },
    ];

    for (const L of layers) {
      const mat = new ShaderMaterial({
        uniforms: {
          uMap: { value: this.tex },
          uColor: { value: new Color(0xc5cde0) },
          uOpacity: { value: L.opacity },
        },
        vertexShader: vert,
        fragmentShader: frag,
        transparent: true,
        depthWrite: false,
        depthTest: true,
        blending: AdditiveBlending,
        side: DoubleSide,
        fog: false,
        toneMapped: true,
      });
      const mesh = new Mesh(new PlaneGeometry(L.w, L.d, 1, 1), mat);
      mesh.rotation.x = -Math.PI / 2;
      if (L.yRot) mesh.rotation.z = L.yRot;
      mesh.position.copy(L.pos);
      mesh.renderOrder = 3;
      mesh.frustumCulled = false;
      this.group.add(mesh);
      this.mats.push(mat);
      // stash base opacity
      (mat.userData as { base: number }).base = L.opacity;
    }
  }

  apply(u: EnvUniformSnapshot): void {
    const col = new Color().setRGB(
      u.fogColor[0] * 0.55 + 0.25,
      u.fogColor[1] * 0.55 + 0.27,
      u.fogColor[2] * 0.55 + 0.32,
    );
    const rainBoost = u.weather === 'rain' ? 1.15 : u.weather === 'overcast' ? 1.05 : 0.75;
    for (const m of this.mats) {
      (m.uniforms.uColor.value as Color).copy(col);
      m.uniforms.uOpacity.value = ((m.userData as { base: number }).base ?? 0.1) * rainBoost;
    }
  }

  dispose(): void {
    this.tex.dispose();
    this.group.traverse((o) => {
      if (o instanceof Mesh) {
        o.geometry.dispose();
        (o.material as ShaderMaterial).dispose();
      }
    });
  }
}
