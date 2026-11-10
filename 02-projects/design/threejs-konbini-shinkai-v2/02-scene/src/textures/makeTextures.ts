import { CanvasTexture, RepeatWrapping, SRGBColorSpace } from 'three';

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('2d context');
  return [c, ctx];
}

function tex(c: HTMLCanvasElement, repeatX = 1, repeatY = 1): CanvasTexture {
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  t.wrapS = RepeatWrapping;
  t.wrapT = RepeatWrapping;
  t.repeat.set(repeatX, repeatY);
  t.needsUpdate = true;
  return t;
}

const JP = '"Noto Sans CJK JP", "Noto Serif CJK JP", "Yu Gothic", "YuGothic", "Meiryo", "Noto Sans JP", sans-serif';

/** Warm tile facade — grout + slight value noise, not plastic flat. */
export function makeFacadeTiles(): CanvasTexture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = '#cfc8bc';
  g.fillRect(0, 0, 512, 512);
  const tw = 64;
  const th = 32;
  for (let y = 0; y < 512; y += th) {
    const odd = Math.floor(y / th) % 2;
    for (let x = -tw; x < 512; x += tw) {
      const xx = x + (odd ? tw * 0.5 : 0);
      const v = 200 + ((xx * 13 + y * 7) % 17);
      g.fillStyle = `rgb(${v + 8},${v},${v - 10})`;
      g.fillRect(xx + 1, y + 1, tw - 2, th - 2);
    }
  }
  g.strokeStyle = 'rgba(90, 82, 74, 0.28)';
  g.lineWidth = 1;
  for (let y = 0; y <= 512; y += th) {
    g.beginPath();
    g.moveTo(0, y + 0.5);
    g.lineTo(512, y + 0.5);
    g.stroke();
  }
  return tex(c, 4, 6);
}

export function makeFloorTiles(): CanvasTexture {
  const [c, g] = canvas(256, 256);
  g.fillStyle = '#d8d0c4';
  g.fillRect(0, 0, 256, 256);
  const s = 32;
  for (let y = 0; y < 256; y += s) {
    for (let x = 0; x < 256; x += s) {
      const alt = ((x + y) / s) % 2 === 0;
      g.fillStyle = alt ? '#e2dcd0' : '#cfc6b8';
      g.fillRect(x + 1, y + 1, s - 2, s - 2);
    }
  }
  return tex(c, 8, 10);
}

export function makeSidewalk(): CanvasTexture {
  const [c, g] = canvas(256, 256);
  g.fillStyle = '#7a7670';
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 1800; i++) {
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    const v = 100 + Math.random() * 40;
    g.fillStyle = `rgba(${v},${v - 4},${v - 10},0.35)`;
    g.fillRect(x, y, 2, 2);
  }
  g.strokeStyle = 'rgba(40,38,36,0.35)';
  g.strokeRect(2, 2, 252, 252);
  return tex(c, 6, 18);
}

/** Color map for the thick lightbox: darker panel, bright glyphs across the width. */
export function makeSign(): CanvasTexture {
  const [c, g] = canvas(2048, 512);
  g.fillStyle = '#5c5852';
  g.fillRect(0, 0, 2048, 512);
  const grd = g.createLinearGradient(0, 0, 0, 512);
  grd.addColorStop(0, 'rgba(255,244,220,0.16)');
  grd.addColorStop(0.5, 'rgba(0,0,0,0)');
  grd.addColorStop(1, 'rgba(0,0,0,0.22)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 2048, 512);

  g.fillStyle = '#c43b32';
  g.fillRect(0, 0, 36, 512);
  g.fillRect(2012, 0, 36, 512);

  g.fillStyle = '#fffaf0';
  g.font = `700 250px ${JP}`;
  g.textAlign = 'left';
  g.textBaseline = 'middle';
  g.fillText('日曜', 100, 250);

  g.font = `700 92px ${JP}`;
  g.fillStyle = '#fff6e4';
  g.fillText('NICHIYOU', 820, 200);
  g.font = `700 70px ${JP}`;
  g.fillStyle = '#ffc8b4';
  g.fillText('24時間', 820, 310);

  g.fillStyle = '#ff6a5a';
  g.fillRect(100, 400, 520, 10);
  return tex(c, 1, 1);
}

/** Emissive map: letters and red ends glow; panel stays nearly black. */
export function makeSignEmissive(): CanvasTexture {
  const [c, g] = canvas(2048, 512);
  g.fillStyle = '#121110';
  g.fillRect(0, 0, 2048, 512);
  g.fillStyle = '#ff4a42';
  g.fillRect(0, 0, 36, 512);
  g.fillRect(2012, 0, 36, 512);

  g.shadowColor = 'rgba(255,236,200,0.85)';
  g.shadowBlur = 12;
  g.fillStyle = '#ffffff';
  g.font = `700 250px ${JP}`;
  g.textAlign = 'left';
  g.textBaseline = 'middle';
  g.fillText('日曜', 100, 250);

  g.font = `700 92px ${JP}`;
  g.fillStyle = '#fff8ec';
  g.fillText('NICHIYOU', 820, 200);
  g.font = `700 70px ${JP}`;
  g.fillStyle = '#ffd0c0';
  g.fillText('24時間', 820, 310);

  g.shadowBlur = 0;
  g.fillStyle = '#ff8870';
  g.fillRect(100, 400, 520, 10);
  return tex(c, 1, 1);
}

/** Small hours card for a window corner — restrained. */
export function makeHoursPoster(): CanvasTexture {
  const [c, g] = canvas(256, 320);
  g.fillStyle = '#f7f3ea';
  g.fillRect(0, 0, 256, 320);
  g.fillStyle = '#2a2a2a';
  g.fillRect(0, 0, 256, 8);
  g.fillStyle = '#222';
  g.font = `700 28px ${JP}`;
  g.textAlign = 'center';
  g.fillText('営業時間', 128, 70);
  g.font = `700 48px ${JP}`;
  g.fillStyle = '#b83232';
  g.fillText('24時間', 128, 150);
  g.font = `500 24px ${JP}`;
  g.fillStyle = '#333';
  g.fillText('年中無休', 128, 210);
  g.fillStyle = '#b83232';
  g.fillRect(70, 240, 116, 4);
  return tex(c, 1, 1);
}

/** Auto-door notice, small and quiet. */
export function makeDoorDecal(): CanvasTexture {
  const [c, g] = canvas(256, 128);
  g.fillStyle = 'rgba(248,248,250,0.88)';
  g.fillRect(0, 0, 256, 128);
  g.strokeStyle = 'rgba(40,40,44,0.55)';
  g.lineWidth = 4;
  g.strokeRect(4, 4, 248, 120);
  g.fillStyle = '#222';
  g.font = `700 36px ${JP}`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText('自動ドア', 128, 52);
  g.font = `500 20px ${JP}`;
  g.fillStyle = '#444';
  g.fillText('ご注意ください', 128, 92);
  return tex(c, 1, 1);
}

/** Sparse wet-glass droplet roughness / bump. Mostly clear, a few beads. */
export function makeGlassDroplets(): CanvasTexture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = '#0a0a0a';
  g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 140; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 512;
    const r = 0.8 + Math.random() * 3.2;
    const grd = g.createRadialGradient(x, y, 0, x, y, r);
    const a = 0.25 + Math.random() * 0.45;
    grd.addColorStop(0, `rgba(220,220,220,${a})`);
    grd.addColorStop(0.7, `rgba(80,80,80,${a * 0.35})`);
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.beginPath();
    g.ellipse(x, y, r, r * (0.7 + Math.random() * 0.5), 0, 0, Math.PI * 2);
    g.fill();
  }
  // a few short drips
  g.globalAlpha = 0.25;
  for (let i = 0; i < 18; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 400;
    g.fillStyle = '#9a9a9a';
    g.fillRect(x, y, 1, 12 + Math.random() * 28);
  }
  g.globalAlpha = 1;
  const t = tex(c, 2, 2);
  t.colorSpace = SRGBColorSpace;
  return t;
}

/** Dark stone / aluminum kickplate, distinct from the tile wall. */
export function makeKickplate(): CanvasTexture {
  const [c, g] = canvas(512, 128);
  g.fillStyle = '#2c3034';
  g.fillRect(0, 0, 512, 128);
  for (let i = 0; i < 900; i++) {
    const v = 36 + Math.random() * 28;
    g.fillStyle = `rgba(${v},${v + 2},${v + 4},0.45)`;
    g.fillRect(Math.random() * 512, Math.random() * 128, 2, 2);
  }
  g.strokeStyle = 'rgba(10,12,14,0.55)';
  g.lineWidth = 2;
  for (let y of [20, 44, 68, 92, 116]) {
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(512, y);
    g.stroke();
  }
  g.strokeStyle = 'rgba(160,166,172,0.18)';
  g.beginPath();
  g.moveTo(0, 6);
  g.lineTo(512, 6);
  g.stroke();
  return tex(c, 8, 1);
}

/** Warm painted-metal soffit, slightly ribbed. */
export function makeSoffit(): CanvasTexture {
  const [c, g] = canvas(512, 256);
  g.fillStyle = '#f3e4c4';
  g.fillRect(0, 0, 512, 256);
  for (let x = 0; x < 512; x += 18) {
    g.fillStyle = 'rgba(210,190,150,0.35)';
    g.fillRect(x, 0, 6, 256);
    g.fillStyle = 'rgba(255,248,230,0.25)';
    g.fillRect(x + 6, 0, 2, 256);
  }
  return tex(c, 8, 2);
}

export function makePoster(kind: 0 | 1 | 2): CanvasTexture {
  const [c, g] = canvas(256, 384);
  const bg = ['#f3efe4', '#ead8c8', '#dce6e4'][kind]!;
  const accent = ['#b83232', '#e8a05a', '#6ec4c0'][kind]!;
  g.fillStyle = bg;
  g.fillRect(0, 0, 256, 384);
  g.fillStyle = accent;
  g.fillRect(0, 0, 256, 28);
  g.fillStyle = '#222';
  g.font = `700 36px ${JP}`;
  g.textAlign = 'center';
  g.fillText(['新作弁当', 'ホットコーヒー', 'フェア'][kind]!, 128, 160);
  g.font = `400 18px ${JP}`;
  g.fillStyle = '#444';
  g.fillText('本日のおすすめ', 128, 210);
  g.fillStyle = accent;
  g.fillRect(80, 240, 96, 6);
  return tex(c, 1, 1);
}

export function makeNeighborWindows(): CanvasTexture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = '#1a2230';
  g.fillRect(0, 0, 512, 512);
  const lights = [
    [40, 60, 50, 70, '#f3d9a8'],
    [120, 80, 40, 50, '#f0c4a0'],
    [220, 40, 46, 64, '#efe6d2'],
    [320, 90, 36, 44, '#f3d9a8'],
    [400, 50, 48, 70, '#e8b898'],
    [60, 200, 44, 58, '#efe6d2'],
    [180, 220, 54, 48, '#1a2230'],
    [280, 180, 40, 66, '#f3d9a8'],
    [380, 210, 50, 50, '#d8a070'],
    [40, 340, 48, 60, '#f0c4a0'],
    [150, 360, 36, 40, '#efe6d2'],
    [250, 330, 60, 70, '#f3d9a8'],
    [360, 350, 42, 52, '#1a2230'],
    [430, 320, 40, 58, '#e8b898'],
  ] as const;
  for (const [x, y, w, h, col] of lights) {
    g.fillStyle = col;
    g.globalAlpha = col === '#1a2230' ? 1 : 0.92;
    g.fillRect(x, y, w, h);
    if (col !== '#1a2230') {
      g.globalAlpha = 0.25;
      g.fillStyle = '#fff6e0';
      g.fillRect(x, y, w, h * 0.35);
    }
    g.globalAlpha = 1;
  }
  return tex(c, 1, 1);
}

export function makeVendingFront(): CanvasTexture {
  const [c, g] = canvas(256, 512);
  g.fillStyle = '#1c242c';
  g.fillRect(0, 0, 256, 512);
  g.fillStyle = '#6ec4c0';
  g.fillRect(16, 12, 224, 18);
  // product rows
  const cols = ['#f5f0e6', '#c43b3b', '#3a6a8a', '#e8a05a', '#dfe8e4', '#8a3a3a'];
  for (let r = 0; r < 5; r++) {
    for (let k = 0; k < 4; k++) {
      const x = 28 + k * 54;
      const y = 48 + r * 70;
      g.fillStyle = '#0e151c';
      g.fillRect(x - 2, y - 2, 44, 58);
      g.fillStyle = cols[(r * 4 + k) % cols.length]!;
      g.fillRect(x + 6, y + 8, 28, 40);
    }
  }
  g.fillStyle = '#2a323a';
  g.fillRect(20, 410, 216, 80);
  for (let i = 0; i < 8; i++) {
    g.fillStyle = i === 2 ? '#e8a05a' : '#3a424a';
    g.beginPath();
    g.arc(44 + (i % 4) * 48, 436 + Math.floor(i / 4) * 32, 8, 0, Math.PI * 2);
    g.fill();
  }
  return tex(c, 1, 1);
}

export function makeNoren(): CanvasTexture {
  const [c, g] = canvas(512, 256);
  g.fillStyle = '#b83232';
  g.fillRect(0, 0, 512, 256);
  // slits
  for (let i = 1; i < 5; i++) {
    g.fillStyle = 'rgba(20,10,10,0.35)';
    g.fillRect(i * 102 - 3, 20, 6, 236);
  }
  g.fillStyle = '#f5f0e6';
  g.font = `700 72px ${JP}`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText('隣', 256, 130);
  return tex(c, 1, 1);
}
