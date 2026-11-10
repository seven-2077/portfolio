import {
  BoxGeometry,
  CanvasTexture,
  CylinderGeometry,
  ExtrudeGeometry,
  Group,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  Shape,
  SRGBColorSpace,
} from 'three';

const JP = '"Noto Sans CJK JP", "Noto Serif CJK JP", "Yu Gothic", sans-serif';

function ctx(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  return [c, g];
}

function tex(c: HTMLCanvasElement): CanvasTexture {
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  t.needsUpdate = true;
  return t;
}

const riceMat = new MeshStandardMaterial({ color: 0xf4eee4, roughness: 0.78 });
const noriMat = new MeshStandardMaterial({ color: 0x10160f, roughness: 0.7 });
const capMat = new MeshStandardMaterial({ color: 0xd8d4cc, roughness: 0.45, metalness: 0.1 });

const labelMats: MeshStandardMaterial[] = [
  new MeshStandardMaterial({ color: 0xe07a6a, roughness: 0.55, emissive: 0x3a1510, emissiveIntensity: 0.15 }), // shake
  new MeshStandardMaterial({ color: 0x3a6a48, roughness: 0.55 }), // kombu
  new MeshStandardMaterial({ color: 0xc45a6a, roughness: 0.55 }), // ume
  new MeshStandardMaterial({ color: 0xd8a05a, roughness: 0.55 }), // tuna mayo
];

function bottleTex(kind: number): CanvasTexture {
  const [c, g] = ctx(64, 256);
  const bodies = ['#2f6a44', '#5a3a28', '#3a6a8a', '#1a1a1c', '#6a4a32'];
  const labels = ['#e8f0d8', '#f0e4c8', '#e6f0f6', '#c4302a', '#3a2a22'];
  const accents = ['#1f4a2e', '#8a5a28', '#2a5a78', '#f5f0e6', '#d8b070'];
  const titles = ['緑茶', '麦茶', '水', 'コーラ', 'コーヒー'];
  g.fillStyle = bodies[kind % bodies.length]!;
  g.fillRect(0, 0, 64, 256);
  g.fillStyle = labels[kind % labels.length]!;
  g.fillRect(4, 70, 56, 110);
  g.fillStyle = accents[kind % accents.length]!;
  g.fillRect(4, 70, 56, 14);
  g.fillStyle = kind === 3 ? '#f5f0e6' : '#222';
  g.font = `700 22px ${JP}`;
  g.textAlign = 'center';
  g.fillText(titles[kind % titles.length]!, 32, 130);
  return tex(c);
}

function cupTex(kind: number): CanvasTexture {
  const [c, g] = ctx(128, 256);
  const lids = ['#c43b2a', '#e07020', '#2a5a8a', '#3a7a48'];
  const bodies = ['#f5efe4', '#f3e6d0', '#e8eef2', '#eef0e4'];
  const names = ['醤油', '味噌', '塩', '担々'];
  g.fillStyle = bodies[kind % 4]!;
  g.fillRect(0, 40, 128, 216);
  g.fillStyle = lids[kind % 4]!;
  g.fillRect(0, 0, 128, 48);
  g.fillStyle = '#222';
  g.font = `700 28px ${JP}`;
  g.textAlign = 'center';
  g.fillText(names[kind % 4]!, 64, 150);
  g.font = `500 16px ${JP}`;
  g.fillText('カップ麺', 64, 180);
  return tex(c);
}

const bottleMats = [0, 1, 2, 3, 4].map(
  (k) =>
    new MeshStandardMaterial({
      map: bottleTex(k),
      roughness: 0.28,
      metalness: 0.08,
    }),
);
const cupMats = [0, 1, 2, 3].map(
  (k) =>
    new MeshStandardMaterial({
      map: cupTex(k),
      roughness: 0.5,
    }),
);
const lidMats = [
  new MeshStandardMaterial({ color: 0xc43b2a, roughness: 0.45 }),
  new MeshStandardMaterial({ color: 0xe07020, roughness: 0.45 }),
  new MeshStandardMaterial({ color: 0x2a5a8a, roughness: 0.45 }),
  new MeshStandardMaterial({ color: 0x3a7a48, roughness: 0.45 }),
];

let onigiriGeo: ExtrudeGeometry | null = null;
function getOnigiriGeo(): ExtrudeGeometry {
  if (onigiriGeo) return onigiriGeo;
  const s = new Shape();
  // Pointed triangle — silhouette must read at Shot 1 distance
  s.moveTo(0, 0.145);
  s.lineTo(0.112, -0.062);
  s.quadraticCurveTo(0, -0.1, -0.112, -0.062);
  s.lineTo(0, 0.145);
  onigiriGeo = new ExtrudeGeometry(s, {
    depth: 0.032,
    bevelEnabled: true,
    bevelThickness: 0.006,
    bevelSize: 0.006,
    bevelSegments: 2,
  });
  onigiriGeo.center();
  return onigiriGeo;
}

const bottleGeo = new CylinderGeometry(0.02, 0.022, 0.2, 10);
const capGeo = new CylinderGeometry(0.016, 0.017, 0.03, 10);
const cupGeo = new CylinderGeometry(0.042, 0.038, 0.11, 12);
const cupLidGeo = new CylinderGeometry(0.044, 0.044, 0.012, 12);

export function makeOnigiri(kind = 0): Group {
  const g = new Group();
  const rice = new Mesh(getOnigiriGeo(), riceMat);
  g.add(rice);
  // Front nori + a waist wrap so the black band reads from a 3/4 view
  const nori = new Mesh(new PlaneGeometry(0.09, 0.09), noriMat);
  nori.position.set(0, -0.032, 0.022);
  g.add(nori);
  const noriBack = new Mesh(new PlaneGeometry(0.09, 0.09), noriMat);
  noriBack.position.set(0, -0.032, -0.022);
  noriBack.rotation.y = Math.PI;
  g.add(noriBack);
  const wrap = new Mesh(new BoxGeometry(0.2, 0.07, 0.038), noriMat);
  wrap.position.set(0, -0.03, 0);
  g.add(wrap);
  const lab = new Mesh(new PlaneGeometry(0.036, 0.022), labelMats[kind % labelMats.length]!);
  lab.position.set(0, 0.028, 0.024);
  g.add(lab);
  g.scale.setScalar(2.05);
  return g;
}

export function makeBottle(kind = 0): Group {
  const g = new Group();
  const body = new Mesh(bottleGeo, bottleMats[kind % bottleMats.length]!);
  body.position.y = 0.1;
  g.add(body);
  const cap = new Mesh(capGeo, capMat);
  cap.position.y = 0.215;
  g.add(cap);
  return g;
}

const riceFood = new MeshStandardMaterial({ color: 0xf3ebd8, roughness: 0.7 });
const salmonFood = new MeshStandardMaterial({ color: 0xd45a3a, roughness: 0.55 });
const eggFood = new MeshStandardMaterial({ color: 0xe8c45a, roughness: 0.5 });
const vegFood = new MeshStandardMaterial({ color: 0x4a8a48, roughness: 0.6 });
const trayMat = new MeshStandardMaterial({ color: 0x1a1a1c, roughness: 0.5 });
const lidMatClear = new MeshStandardMaterial({
  color: 0xd8e8f0,
  roughness: 0.12,
  metalness: 0.05,
  transparent: true,
  opacity: 0.28,
});

export function makeBento(): Group {
  const g = new Group();
  const tray = new Mesh(new BoxGeometry(0.22, 0.035, 0.16), trayMat);
  tray.position.y = 0.018;
  g.add(tray);
  // Food as real blocks so the lid pattern reads at Shot 1 distance
  const rice = new Mesh(new BoxGeometry(0.1, 0.03, 0.14), riceFood);
  rice.position.set(-0.045, 0.048, 0);
  g.add(rice);
  const sal = new Mesh(new BoxGeometry(0.09, 0.028, 0.065), salmonFood);
  sal.position.set(0.05, 0.048, 0.035);
  g.add(sal);
  const egg = new Mesh(new BoxGeometry(0.09, 0.024, 0.035), eggFood);
  egg.position.set(0.05, 0.046, -0.02);
  g.add(egg);
  const veg = new Mesh(new BoxGeometry(0.09, 0.024, 0.03), vegFood);
  veg.position.set(0.05, 0.046, -0.055);
  g.add(veg);
  const lid = new Mesh(new BoxGeometry(0.23, 0.012, 0.17), lidMatClear);
  lid.position.y = 0.07;
  g.add(lid);
  const band = new Mesh(new BoxGeometry(0.232, 0.008, 0.172), new MeshStandardMaterial({ color: 0xb83232, roughness: 0.45 }));
  band.position.y = 0.064;
  g.add(band);
  // Face the colorful lid toward the glass / camera
  g.rotation.x = -1.05;
  g.scale.setScalar(1.35);
  return g;
}

export function makeCupNoodle(kind = 0): Group {
  const g = new Group();
  const cup = new Mesh(cupGeo, cupMats[kind % cupMats.length]!);
  cup.position.y = 0.055;
  g.add(cup);
  const lid = new Mesh(cupLidGeo, lidMats[kind % lidMats.length]!);
  lid.position.y = 0.116;
  g.add(lid);
  return g;
}

/** A facing gondola already stocked for one category. */
export function stockedShelf(opts: {
  kind: 'onigiri' | 'bottle' | 'bento' | 'cup';
  rows?: number;
  cols?: number;
  width?: number;
}): Group {
  const rows = opts.rows ?? 4;
  const cols = opts.cols ?? 8;
  const width = opts.width ?? 1.7;
  const steel = new MeshStandardMaterial({ color: 0x8a8f94, roughness: 0.45, metalness: 0.55 });
  const board = new MeshStandardMaterial({ color: 0xd8d2c8, roughness: 0.7 });
  const g = new Group();
  const depth = opts.kind === 'bento' ? 0.42 : 0.36;
  g.add(mesh(new BoxGeometry(width, 0.1, depth), steel, 0, 0.05, 0));
  g.add(mesh(new BoxGeometry(0.04, 1.72, depth), steel, -width * 0.48, 0.9, 0));
  g.add(mesh(new BoxGeometry(0.04, 1.72, depth), steel, width * 0.48, 0.9, 0));
  const rowH = 1.55 / rows;
  for (let r = 0; r < rows; r++) {
    const y = 0.22 + r * rowH;
    g.add(mesh(new BoxGeometry(width, 0.03, depth), board, 0, y, 0));
    for (let c = 0; c < cols; c++) {
      const x = -width * 0.42 + (c / Math.max(cols - 1, 1)) * width * 0.84;
      let item: Group;
      if (opts.kind === 'onigiri') item = makeOnigiri((c + r) % 4);
      else if (opts.kind === 'bottle') item = makeBottle((c + r) % 5);
      else if (opts.kind === 'bento') item = makeBento();
      else item = makeCupNoodle((c + r) % 4);
      item.position.set(x, y + 0.02, opts.kind === 'bento' ? 0.08 : 0.02);
      if (opts.kind === 'onigiri') item.rotation.y = 0.32;
      if (opts.kind === 'bento') item.rotation.y = 0.28 + (c % 2 === 0 ? -1 : 1) * 0.04;
      g.add(item);
    }
  }
  return g;
}

function mesh(geo: BoxGeometry, mat: MeshStandardMaterial, x: number, y: number, z: number): Mesh {
  const m = new Mesh(geo, mat);
  m.position.set(x, y, z);
  return m;
}
