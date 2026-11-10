import {
  AdditiveBlending,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  CatmullRomCurve3,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DoubleSide,
  DynamicDrawUsage,
  ExtrudeGeometry,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  Points,
  PointsMaterial,
  Quaternion,
  RepeatWrapping,
  Shape,
  SphereGeometry,
  SRGBColorSpace,
  Texture,
  TubeGeometry,
  Vector3,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';

/**
 * Shinkai v2 surroundings: one store in a quiet edge-of-town.
 * Hero sakura frames the left; the commuter train stays a distant accent.
 */

const RAIL_Z = -46;
const RAIL_Y = 1.65;
const STILL_TRAIN_X = 40;

function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function grassTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 256;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.fillStyle = '#5a6e4c';
  g.fillRect(0, 0, 256, 256);
  const r = rng(7);
  for (let i = 0; i < 2600; i++) {
    const x = r() * 256;
    const y = r() * 256;
    const v = r();
    g.fillStyle =
      v < 0.5
        ? `rgba(70,96,58,${0.25 + r() * 0.3})`
        : v < 0.85
          ? `rgba(110,128,80,${0.2 + r() * 0.25})`
          : `rgba(150,140,96,${0.15 + r() * 0.2})`;
    g.fillRect(x, y, 1 + r() * 2, 2 + r() * 4);
  }
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.wrapS = RepeatWrapping;
  t.wrapT = RepeatWrapping;
  t.repeat.set(40, 40);
  t.anisotropy = 8;
  return t;
}

function petalSprite(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 32;
  c.height = 32;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  const grad = g.createRadialGradient(16, 16, 0, 16, 16, 15);
  grad.addColorStop(0, 'rgba(255,240,244,1)');
  grad.addColorStop(0.55, 'rgba(250,210,220,0.85)');
  grad.addColorStop(1, 'rgba(250,210,220,0)');
  g.fillStyle = grad;
  g.beginPath();
  g.ellipse(16, 16, 15, 9, 0.6, 0, Math.PI * 2);
  g.fill();
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  return t;
}

/** Single sakura petal with a notched tip and soft alpha — not a hard diamond. */
function sakuraPetalTexture(): CanvasTexture {
  const s = 96;
  const c = document.createElement('canvas');
  c.width = s;
  c.height = s;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.clearRect(0, 0, s, s);
  g.translate(s * 0.5, s * 0.58);
  g.beginPath();
  g.moveTo(0, 30);
  g.bezierCurveTo(26, 18, 30, -8, 11, -32);
  g.quadraticCurveTo(0, -18, -11, -32);
  g.bezierCurveTo(-30, -8, -26, 18, 0, 30);
  const grad = g.createRadialGradient(0, 2, 2, 0, 4, 40);
  grad.addColorStop(0, 'rgba(255,250,252,0.55)');
  grad.addColorStop(0.28, 'rgba(255,226,234,0.85)');
  grad.addColorStop(0.62, 'rgba(240,180,196,0.55)');
  grad.addColorStop(0.86, 'rgba(230,160,178,0.18)');
  grad.addColorStop(1, 'rgba(220,150,168,0)');
  g.fillStyle = grad;
  g.fill();
  g.strokeStyle = 'rgba(214,150,168,0.22)';
  g.lineWidth = 0.8;
  g.beginPath();
  g.moveTo(0, 22);
  g.quadraticCurveTo(0, 0, 0, -16);
  g.stroke();
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/** Five-petal flower card for mid / far canopies. */
function sakuraFlowerTexture(): CanvasTexture {
  const s = 128;
  const c = document.createElement('canvas');
  c.width = s;
  c.height = s;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.clearRect(0, 0, s, s);
  g.translate(s * 0.5, s * 0.5);
  for (let i = 0; i < 5; i++) {
    g.save();
    g.rotate((i * Math.PI * 2) / 5);
    g.beginPath();
    g.moveTo(0, 4);
    g.bezierCurveTo(14, 10, 18, 28, 6, 46);
    g.quadraticCurveTo(0, 36, -6, 46);
    g.bezierCurveTo(-18, 28, -14, 10, 0, 4);
    const grad = g.createLinearGradient(0, 4, 0, 46);
    grad.addColorStop(0, 'rgba(255,248,250,0.95)');
    grad.addColorStop(0.55, 'rgba(250,210,222,0.85)');
    grad.addColorStop(1, 'rgba(230,160,180,0)');
    g.fillStyle = grad;
    g.fill();
    g.restore();
  }
  const core = g.createRadialGradient(0, 0, 0, 0, 0, 10);
  core.addColorStop(0, 'rgba(255,248,230,0.9)');
  core.addColorStop(1, 'rgba(255,220,180,0)');
  g.fillStyle = core;
  g.beginPath();
  g.arc(0, 0, 10, 0, Math.PI * 2);
  g.fill();
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

interface SakuraTree {
  canopy: Group;
  seed: number;
}

interface PetalSunUniforms {
  uSunDir: { value: Vector3 };
  uSunColor: { value: Color };
}

export class Nature {
  readonly group = new Group();

  private blossomMat!: MeshStandardMaterial;
  private blossomFarMat!: MeshStandardMaterial;
  private flowerMat!: MeshStandardMaterial;
  private trainWinGlass: MeshPhysicalMaterial;
  private trainBodyMat: MeshPhysicalMaterial;
  private trainRoofMat: MeshPhysicalMaterial;
  private trainWinInner: MeshStandardMaterial;
  private railSteel: MeshPhysicalMaterial;
  private lampHead: MeshStandardMaterial;
  private trees: SakuraTree[] = [];
  private train = new Group();
  private petals: Points;
  private petalVel: Float32Array;
  private petalBounds = { minX: -16, maxX: -1, minY: 0.05, maxY: 8.5, minZ: -4, maxZ: 9 };
  private petalSun: PetalSunUniforms[] = [];
  private stillMode = false;

  constructor() {
    this.group.name = 'nature';

    this.blossomMat = this.makePetalMaterial(sakuraPetalTexture(), 0xf8e4ea, false);
    this.blossomFarMat = this.makePetalMaterial(sakuraPetalTexture(), 0xe8c8d2, true);
    this.flowerMat = this.makePetalMaterial(sakuraFlowerTexture(), 0xf4dce4, false);

    this.trainBodyMat = new MeshPhysicalMaterial({
      color: 0x5a616a,
      map: bodyStreakTexture(),
      roughness: 0.28,
      roughnessMap: bodyStreakTexture(),
      metalness: 0.72,
      clearcoat: 0.95,
      clearcoatRoughness: 0.12,
      envMapIntensity: 1.7,
    });
    this.trainRoofMat = new MeshPhysicalMaterial({
      color: 0x3e444c,
      roughness: 0.38,
      metalness: 0.75,
      envMapIntensity: 1.15,
    });
    this.trainWinGlass = new MeshPhysicalMaterial({
      color: 0x121c28,
      roughness: 0.02,
      metalness: 0.35,
      transparent: true,
      opacity: 0.2,
      envMapIntensity: 4.2,
      clearcoat: 1,
      clearcoatRoughness: 0.03,
    });
    this.trainWinGlass.onBeforeCompile = (shader) => {
      shader.uniforms.uSkyHor = { value: new Color(0xf4a070) };
      shader.uniforms.uSkyZen = { value: new Color(0x6a4a78) };
      this.trainWinGlass.userData.uSkyHor = shader.uniforms.uSkyHor;
      this.trainWinGlass.userData.uSkyZen = shader.uniforms.uSkyZen;
      shader.fragmentShader = shader.fragmentShader
        .replace(
          'void main() {',
          'uniform vec3 uSkyHor;\nuniform vec3 uSkyZen;\nvoid main() {',
        )
        .replace(
          '#include <opaque_fragment>',
          'vec3 vDirW = normalize(vViewPosition);\n' +
            'vec3 nW = normalize(normal);\n' +
            'vec3 r = reflect(-vDirW, nW);\n' +
            'float skyF = pow(1.0 - clamp(dot(nW, vDirW), 0.0, 1.0), 1.6);\n' +
            'vec3 skyC = mix(uSkyHor, uSkyZen, clamp(r.y * 0.5 + 0.5, 0.0, 1.0));\n' +
            'outgoingLight += skyC * skyF * 0.7;\n' +
            '#include <opaque_fragment>',
        );
    };
    this.trainWinGlass.customProgramCacheKey = () => 'train-win-sky-v5';
    this.trainWinInner = new MeshStandardMaterial({
      color: 0xffe2b8,
      emissive: new Color(0xffc070),
      emissiveIntensity: 1.7,
      roughness: 0.5,
    });
    this.railSteel = new MeshPhysicalMaterial({
      color: 0xc4c0b8,
      roughness: 0.16,
      metalness: 0.96,
      envMapIntensity: 1.5,
      clearcoat: 0.35,
    });
    this.lampHead = new MeshStandardMaterial({
      color: 0xffe2b0,
      emissive: new Color(0xffd08a),
      emissiveIntensity: 1.2,
    });

    this.buildGround();
    this.buildEmbankment();
    this.buildRailway();
    this.buildTrain();

    this.addSakura(new Vector3(-7.9, 0, 6.6), 1.36, 11, {
      role: 'frame',
      leanToward: new Vector3(0.85, 0.35, -0.25),
    });
    this.addSakura(new Vector3(-13.6, 0, -1.8), 1.05, 23, { role: 'mid' });
    this.addSakura(new Vector3(-22.5, 0, -14), 0.88, 37, { role: 'far' });
    this.addSakura(new Vector3(18.5, 0, -20), 0.8, 53, { role: 'far' });

    this.buildPoleAndLamp();

    const { points, vel } = this.buildPetals(260);
    this.petals = points;
    this.petalVel = vel;
    this.group.add(points);
  }

  private makePetalMaterial(map: CanvasTexture, color: number, far: boolean): MeshStandardMaterial {
    const mat = new MeshStandardMaterial({
      map,
      color,
      transparent: true,
      alphaTest: 0.06,
      depthWrite: true,
      roughness: 0.55,
      metalness: 0,
      side: DoubleSide,
      emissive: new Color(Hex.sakuraBelt),
      emissiveIntensity: far ? 0.01 : 0.03,
      vertexColors: true,
    });
    mat.onBeforeCompile = (shader) => {
      const uniforms: PetalSunUniforms = {
        uSunDir: { value: new Vector3(-0.6, 0.28, -0.7) },
        uSunColor: { value: new Color(0xffc888) },
      };
      shader.uniforms.uSunDir = uniforms.uSunDir;
      shader.uniforms.uSunColor = uniforms.uSunColor;
      this.petalSun.push(uniforms);
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>\nuniform vec3 uSunDir;\nuniform vec3 uSunColor;`,
        )
        .replace(
          '#include <opaque_fragment>',
          `
          vec3 nrm = normalize(vNormal);
          vec3 sunL = normalize(uSunDir);
          float ndl = dot(nrm, sunL);
          float wrap = ndl * 0.5 + 0.5;
          float backLit = pow(clamp(-ndl, 0.0, 1.0), 0.8);
          vec3 trans = mix(vec3(1.0, 0.78, 0.84), uSunColor, 0.5);
          outgoingLight *= mix(0.7, 1.08, wrap);
          outgoingLight += trans * backLit * ${far ? '0.45' : '0.9'} * diffuseColor.a;
          #include <opaque_fragment>
          `,
        );
    };
    return mat;
  }

  // ---------------------------------------------------------------- ground
  private buildGround(): void {
    const grassMat = new MeshStandardMaterial({
      map: grassTexture(),
      color: 0x7a8c6c,
      roughness: 0.82,
      metalness: 0.04,
    });
    this.tintGrass(grassMat);
    const ground = new Mesh(new PlaneGeometry(280, 280), grassMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, -0.03, -50);
    ground.receiveShadow = true;
    this.group.add(ground);

    const blade = new ConeGeometry(0.035, 0.38, 3);
    blade.translate(0, 0.19, 0);
    const tuftMat = new MeshStandardMaterial({ color: 0x6a8058, roughness: 0.9 });
    const count = 1800;
    const tufts = new InstancedMesh(blade, tuftMat, count);
    const r = rng(91);
    const m = new Matrix4();
    const q = new Quaternion();
    const s = new Vector3();
    const p = new Vector3();
    const tint = new Color();
    let n = 0;
    let guard = 0;
    while (n < count && guard < count * 8) {
      guard++;
      const x = -36 + r() * 72;
      const z = -36 + r() * 34;
      if (x > -5.2 && x < 5.2 && z > -8.5) continue;
      if (z > -0.4) continue;
      if (Math.abs(z - RAIL_Z) < 2.2) continue;
      const onBank = Math.abs(z - RAIL_Z) < 7 ? (1 - Math.abs(z - RAIL_Z) / 7) * RAIL_Y : 0;
      p.set(x, onBank - 0.02, z);
      q.setFromAxisAngle(new Vector3(r() - 0.5, 0, r() - 0.5).normalize(), (r() - 0.5) * 0.5);
      const h = 0.6 + r() * 0.9;
      s.set(1, h, 1);
      m.compose(p, q, s);
      tufts.setMatrixAt(n, m);
      tint.setHSL(0.24 + r() * 0.06, 0.25 + r() * 0.15, 0.3 + r() * 0.14);
      tufts.setColorAt(n, tint);
      n++;
    }
    tufts.instanceMatrix.needsUpdate = true;
    tufts.castShadow = false;
    tufts.receiveShadow = true;
    this.group.add(tufts);
  }

  private buildEmbankment(): void {
    const shape = new Shape();
    shape.moveTo(-7, 0);
    shape.lineTo(-2.0, RAIL_Y);
    shape.lineTo(2.0, RAIL_Y);
    shape.lineTo(7, 0);
    shape.lineTo(-7, 0);
    const geo = new ExtrudeGeometry(shape, { depth: 240, bevelEnabled: false, steps: 1 });
    geo.rotateY(Math.PI / 2);
    geo.translate(-120, 0, 0);
    const bankMat = new MeshStandardMaterial({
      map: grassTexture(),
      color: 0x8c9c78,
      roughness: 0.9,
    });
    this.tintGrass(bankMat);
    const bank = new Mesh(geo, bankMat);
    bank.position.set(0, -0.02, RAIL_Z);
    bank.receiveShadow = true;
    this.group.add(bank);

    // Approach slope on the RIGHT of the store, rising TOWARD the camera
    // from mid-ground up to the rails. (Previous berm extruded away from the lens.)
    // rotY(+PI/2): (x,y,z) -> (z,y,-x); world z = RAIL_Z - x, so x<0 is toward the camera.
    const startX = 6.8;
    const widthX = 40;
    const approach = new Shape();
    approach.moveTo(2.6, 0);
    approach.lineTo(2.6, RAIL_Y);
    approach.lineTo(-2.8, RAIL_Y);
    approach.lineTo(-9, RAIL_Y * 0.75);
    approach.lineTo(-20, RAIL_Y * 0.38);
    approach.lineTo(-34, 0);
    approach.lineTo(2.6, 0);
    const appGeo = new ExtrudeGeometry(approach, { depth: widthX, bevelEnabled: false, steps: 1 });
    appGeo.rotateY(Math.PI / 2);
    const appMat = new MeshStandardMaterial({
      map: grassTexture(),
      color: 0x6f8060,
      roughness: 0.88,
    });
    this.tintGrass(appMat);
    const app = new Mesh(appGeo, appMat);
    app.position.set(startX, -0.02, RAIL_Z);
    app.receiveShadow = true;
    this.group.add(app);

    // Darker earth cut on the upper face, so the rise doesn't melt into the field
    const cut = new Shape();
    cut.moveTo(-2.8, RAIL_Y);
    cut.lineTo(-9, RAIL_Y * 0.75);
    cut.lineTo(-20, RAIL_Y * 0.38);
    cut.lineTo(-20, RAIL_Y * 0.28);
    cut.lineTo(-9, RAIL_Y * 0.62);
    cut.lineTo(-2.8, RAIL_Y - 0.12);
    cut.lineTo(-2.8, RAIL_Y);
    const cutGeo = new ExtrudeGeometry(cut, { depth: widthX, bevelEnabled: false, steps: 1 });
    cutGeo.rotateY(Math.PI / 2);
    const cutMesh = new Mesh(
      cutGeo,
      new MeshStandardMaterial({ color: 0x5a4e42, roughness: 0.92 }),
    );
    cutMesh.position.set(startX, -0.01, RAIL_Z);
    cutMesh.receiveShadow = true;
    this.group.add(cutMesh);
  }

  // --------------------------------------------------------------- railway
  private buildRailway(): void {
    const ballastMat = new MeshStandardMaterial({
      map: ballastTexture(),
      color: 0x9a9488,
      roughness: 0.86,
    });
    const ballast = new Mesh(new BoxGeometry(240, 0.34, 5.6), ballastMat);
    ballast.position.set(0, RAIL_Y + 0.08, RAIL_Z);
    ballast.receiveShadow = true;
    this.group.add(ballast);
    // Slightly raised shoulder so the bed reads against the grass slope
    const shoulder = new Mesh(new BoxGeometry(240, 0.16, 6.6), ballastMat);
    shoulder.position.set(0, RAIL_Y - 0.04, RAIL_Z);
    shoulder.receiveShadow = true;
    this.group.add(shoulder);

    for (const dz of [-0.7, 0.7]) {
      const rail = new Mesh(new BoxGeometry(240, 0.18, 0.32), this.railSteel);
      rail.position.set(0, RAIL_Y + 0.36, RAIL_Z + dz);
      this.group.add(rail);
      const glint = new Mesh(
        new BoxGeometry(240, 0.03, 0.12),
        new MeshPhysicalMaterial({
          color: 0xddd8d0,
          roughness: 0.1,
          metalness: 1,
          envMapIntensity: 1.8,
        }),
      );
      glint.position.set(0, RAIL_Y + 0.46, RAIL_Z + dz);
      this.group.add(glint);
    }

    const sleeperGeo = new BoxGeometry(0.55, 0.2, 2.85);
    const sleeperMat = new MeshStandardMaterial({
      map: sleeperTexture(),
      color: 0xffffff,
      roughness: 0.82,
    });
    const spacing = 0.86;
    const total = Math.floor(240 / spacing);
    const sleepers = new InstancedMesh(sleeperGeo, sleeperMat, total);
    const o = new Object3D();
    for (let i = 0; i < total; i++) {
      o.position.set(-120 + i * spacing, RAIL_Y + 0.28, RAIL_Z);
      o.rotation.y = ((i % 5) - 2) * 0.012;
      o.updateMatrix();
      sleepers.setMatrixAt(i, o.matrix);
    }
    sleepers.instanceMatrix.needsUpdate = true;
    this.group.add(sleepers);

    const mastMat = new MeshStandardMaterial({ color: 0x4a5058, roughness: 0.48, metalness: 0.55 });
    const wireMat = new MeshStandardMaterial({ color: 0x1c1c1e, roughness: 0.5, metalness: 0.4 });
    const mastXs: number[] = [];
    for (let x = -112; x <= 112; x += 16) mastXs.push(x);
    for (const x of mastXs) {
      const mast = new Mesh(new CylinderGeometry(0.1, 0.14, 5.4, 8), mastMat);
      mast.position.set(x, RAIL_Y + 2.7, RAIL_Z - 2.15);
      mast.castShadow = true;
      this.group.add(mast);
      const arm = new Mesh(new BoxGeometry(0.07, 0.07, 2.5), mastMat);
      arm.position.set(x, RAIL_Y + 5.15, RAIL_Z - 0.95);
      this.group.add(arm);
    }
    for (let i = 0; i < mastXs.length - 1; i++) {
      const a = new Vector3(mastXs[i]!, RAIL_Y + 5.4, RAIL_Z);
      const b = new Vector3(mastXs[i + 1]!, RAIL_Y + 5.4, RAIL_Z);
      this.group.add(sagWire(a, b, 0.32, wireMat, 0.014));
    }
    const contact = new Mesh(new BoxGeometry(240, 0.02, 0.02), wireMat);
    contact.position.set(0, RAIL_Y + 4.85, RAIL_Z);
    this.group.add(contact);

    // Soft air along the right-hand railway — not a decorative shaft
    const haze = new Mesh(
      new PlaneGeometry(64, 7),
      new MeshBasicMaterial({
        color: 0xc5ced8,
        transparent: true,
        opacity: 0.1,
        depthWrite: false,
        fog: true,
        blending: AdditiveBlending,
        side: DoubleSide,
      }),
    );
    haze.rotation.x = -Math.PI / 2;
    haze.position.set(22, RAIL_Y + 2.6, RAIL_Z);
    haze.renderOrder = 3;
    this.group.add(haze);
  }

  private buildTrain(): void {
    const stripeMat = new MeshStandardMaterial({ color: 0x2f5e5a, roughness: 0.4, metalness: 0.35 });
    const skirtMat = new MeshStandardMaterial({ color: 0x24262a, roughness: 0.52, metalness: 0.45 });
    const beltMat = new MeshStandardMaterial({ color: 0x2a3038, roughness: 0.42, metalness: 0.5 });
    const frameMat = new MeshStandardMaterial({ color: 0x1c2228, roughness: 0.38, metalness: 0.55 });
    const cornerR = 0.22;

    const carLen = 12.0;
    const gap = 0.45;
    const cars = 3;
    for (let c = 0; c < cars; c++) {
      const car = new Group();
      car.position.x = -c * (carLen + gap);

      const h = 2.45;
      const w = 2.7;
      const bodyY = 0.72 + h * 0.5;
      const core = new Mesh(
        new BoxGeometry(carLen - cornerR * 2, h, w - cornerR * 2),
        this.trainBodyMat,
      );
      core.position.y = bodyY;
      core.castShadow = true;
      car.add(core);
      // vertical corner fillets — break the cardboard-box silhouette
      for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) {
          const cyl = new Mesh(
            new CylinderGeometry(cornerR, cornerR, h, 12),
            this.trainBodyMat,
          );
          cyl.position.set(sx * (carLen * 0.5 - cornerR), bodyY, sz * (w * 0.5 - cornerR));
          cyl.castShadow = true;
          car.add(cyl);
        }
      }
      // side and end slabs to fill between fillets
      const side = new Mesh(new BoxGeometry(carLen - cornerR * 2, h, cornerR * 2), this.trainBodyMat);
      side.position.set(0, bodyY, w * 0.5 - cornerR);
      side.castShadow = true;
      car.add(side);
      const side2 = side.clone();
      side2.position.z *= -1;
      car.add(side2);
      const end = new Mesh(new BoxGeometry(cornerR * 2, h, w - cornerR * 2), this.trainBodyMat);
      end.position.set(carLen * 0.5 - cornerR, bodyY, 0);
      car.add(end);
      const end2 = end.clone();
      end2.position.x *= -1;
      car.add(end2);

      const roof = new Mesh(
        new CylinderGeometry(1.35, 1.35, carLen, 16, 1, false, -Math.PI / 2, Math.PI),
        this.trainRoofMat,
      );
      roof.rotation.z = Math.PI / 2;
      roof.scale.set(1, 1, 0.22);
      roof.position.y = 3.18;
      car.add(roof);

      // Roof drip rail / gutter — breaks the regular box silhouette
      const drip = new Mesh(
        new BoxGeometry(carLen - 0.15, 0.06, 2.62),
        new MeshStandardMaterial({ color: 0x2a3036, roughness: 0.35, metalness: 0.7 }),
      );
      drip.position.y = 3.02;
      car.add(drip);
      const skirt = new Mesh(new BoxGeometry(carLen - 0.4, 0.48, 2.35), skirtMat);
      skirt.position.y = 0.38;
      car.add(skirt);

      const bogieMat = new MeshStandardMaterial({ color: 0x2a2c30, roughness: 0.45, metalness: 0.6 });
      const wheelMat = new MeshStandardMaterial({ color: 0x1a1a1c, roughness: 0.4, metalness: 0.7 });
      for (const bx of [-3.6, 3.6]) {
        const bogie = new Mesh(new BoxGeometry(2.0, 0.28, 2.15), bogieMat);
        bogie.position.set(bx, 0.22, 0);
        car.add(bogie);
        for (const wx of [-0.65, 0.65]) {
          for (const wz of [-0.85, 0.85]) {
            const wh = new Mesh(new CylinderGeometry(0.28, 0.28, 0.14, 12), wheelMat);
            wh.rotation.z = Math.PI / 2;
            wh.position.set(bx + wx, 0.28, wz);
            car.add(wh);
          }
        }
      }

      for (const sd of [1, -1]) {
        // recessed dark window belt — reads as a band, not a flat box face
        const belt = new Mesh(new BoxGeometry(carLen - 0.2, 1.08, 0.1), beltMat);
        belt.position.set(0, 2.28, sd * (w * 0.5 - 0.02));
        car.add(belt);
        const stripe = new Mesh(new PlaneGeometry(carLen - 0.18, 0.18), stripeMat);
        stripe.position.set(0, 1.18, sd * (w * 0.5 + 0.01));
        if (sd < 0) stripe.rotation.y = Math.PI;
        car.add(stripe);

        const seamMat = new MeshStandardMaterial({ color: 0x2a3036, roughness: 0.35, metalness: 0.7 });
        for (const dx of [-3.15, -0.05, 3.1]) {
          const seam = new Mesh(new BoxGeometry(0.045, 2.35, 0.05), seamMat);
          seam.position.set(dx, 1.65, sd * (w * 0.5 + 0.02));
          car.add(seam);
        }
        const wetHi = new Mesh(
          new PlaneGeometry(carLen - 0.5, 0.1),
          new MeshPhysicalMaterial({
            color: 0xc8d0d8,
            roughness: 0.12,
            metalness: 0.9,
            transparent: true,
            opacity: 0.35,
            envMapIntensity: 1.6,
          }),
        );
        wetHi.position.set(0, 1.72, sd * (w * 0.5 + 0.015));
        if (sd < 0) wetHi.rotation.y = Math.PI;
        car.add(wetHi);

        // continuous warm interior band, then framed panes + glass
        const glow = new Mesh(new PlaneGeometry(carLen - 0.6, 0.82), this.trainWinInner);
        glow.position.set(0, 2.28, sd * (w * 0.5 - 0.06));
        if (sd < 0) glow.rotation.y = Math.PI;
        car.add(glow);

        for (let wdw = 0; wdw < 6; wdw++) {
          const x = -carLen * 0.5 + 1.15 + wdw * 1.9;
          const frame = new Mesh(new BoxGeometry(1.46, 0.96, 0.05), frameMat);
          frame.position.set(x, 2.28, sd * (w * 0.5 + 0.02));
          car.add(frame);
          const inner = new Mesh(new PlaneGeometry(1.24, 0.76), this.trainWinInner);
          inner.position.set(x, 2.28, sd * (w * 0.5 + 0.03));
          if (sd < 0) inner.rotation.y = Math.PI;
          car.add(inner);
          const glass = new Mesh(new PlaneGeometry(1.3, 0.82), this.trainWinGlass);
          glass.position.set(x, 2.28, sd * (w * 0.5 + 0.055));
          if (sd < 0) glass.rotation.y = Math.PI;
          car.add(glass);
        }
      }

      if (c === 0) {
        const nose = new Mesh(
          new BoxGeometry(0.22, 1.0, 2.15),
          new MeshPhysicalMaterial({
            color: 0x1a2228,
            roughness: 0.12,
            metalness: 0.8,
            clearcoat: 0.7,
            envMapIntensity: 1.4,
          }),
        );
        nose.position.set(carLen * 0.5 + 0.02, 2.35, 0);
        car.add(nose);
        const screen = new Mesh(new PlaneGeometry(1.8, 0.7), this.trainWinGlass);
        screen.position.set(carLen * 0.5 + 0.14, 2.42, 0);
        screen.rotation.y = Math.PI / 2;
        car.add(screen);
        const head = new Mesh(new SphereGeometry(0.1, 10, 8), this.lampHead);
        head.position.set(carLen * 0.5 + 0.1, 0.98, 0.75);
        car.add(head);
        const head2 = head.clone();
        head2.position.z = -0.75;
        car.add(head2);
      }
      if (c % 2 === 1) {
        const panto = new Mesh(new BoxGeometry(1.15, 0.035, 1.3), this.trainRoofMat);
        panto.position.set(0, 3.9, 0);
        car.add(panto);
        const rod = new Mesh(new CylinderGeometry(0.018, 0.018, 0.85, 6), this.trainRoofMat);
        rod.position.set(0, 3.5, 0);
        rod.rotation.z = 0.5;
        car.add(rod);
      }
      this.train.add(car);
    }
    this.train.position.set(STILL_TRAIN_X, RAIL_Y + 0.36, RAIL_Z);
    this.group.add(this.train);
  }

  // ---------------------------------------------------------------- sakura
  private addSakura(
    at: Vector3,
    scale: number,
    seed: number,
    opts: { role: 'frame' | 'mid' | 'far'; leanToward?: Vector3 } = { role: 'mid' },
  ): void {
    const r = rng(seed);
    const tree = new Group();
    tree.position.copy(at);
    tree.scale.setScalar(scale);
    if (opts.role !== 'frame') tree.rotation.y = r() * Math.PI * 2;

    const bark = new MeshStandardMaterial({
      color: opts.role === 'far' ? 0x5a534c : opts.role === 'mid' ? 0x4a3c36 : 0x3a2c28,
      roughness: 0.86,
    });

    let lean = (r() - 0.5) * 0.45;
    if (opts.leanToward) lean = 0.55;
    const trunkCurve = new CatmullRomCurve3([
      new Vector3(0, 0, 0),
      new Vector3(lean * 0.28, 1.05, 0.08),
      new Vector3(lean * 0.7, 2.15, -0.04),
      new Vector3(lean, 2.85, 0),
    ]);
    const trunk = new Mesh(new TubeGeometry(trunkCurve, 18, 0.17, 8, false), bark);
    trunk.castShadow = true;
    tree.add(trunk);
    const flare = new Mesh(new CylinderGeometry(0.2, 0.32, 0.42, 10), bark);
    flare.position.y = 0.2;
    tree.add(flare);

    const canopy = new Group();
    tree.add(canopy);

    const top = new Vector3(lean, 2.85, 0);
    const tips: Vector3[] = [];
    const branchCount = opts.role === 'frame' ? 8 : opts.role === 'mid' ? 6 : 5;

    for (let i = 0; i < branchCount; i++) {
      let a = (i / branchCount) * Math.PI * 2 + r() * 0.35;
      // Hero tree: bias several branches toward the store / open sky
      if (opts.leanToward && i < 4) {
        a = Math.atan2(opts.leanToward.z, opts.leanToward.x) + (i - 1.5) * 0.38;
      }
      const reach = (opts.role === 'frame' ? 2.0 : 1.5) + r() * 1.15;
      const rise = 1.15 + r() * 1.45;
      const tip = new Vector3(top.x + Math.cos(a) * reach, top.y + rise, top.z + Math.sin(a) * reach);
      const mid = top.clone().lerp(tip, 0.5);
      mid.y += 0.4 + r() * 0.2;
      const curve = new CatmullRomCurve3([top.clone(), mid, tip]);
      const br = new Mesh(new TubeGeometry(curve, 12, 0.05 + r() * 0.03, 6, false), bark);
      br.castShadow = true;
      canopy.add(br);
      tips.push(tip);

      // Secondary twigs — give the canopy a readable branch direction
      const twigs = opts.role === 'far' ? 1 : 2;
      for (let t = 0; t < twigs; t++) {
        const twA = a + (t === 0 ? -1 : 1) * (0.35 + r() * 0.3);
        const twLen = 0.7 + r() * 0.7;
        const twTip = tip
          .clone()
          .add(
            new Vector3(Math.cos(twA) * twLen, 0.25 + r() * 0.45, Math.sin(twA) * twLen),
          );
        const tw = new Mesh(
          new TubeGeometry(new CatmullRomCurve3([tip.clone(), twTip]), 6, 0.018 + r() * 0.01, 5, false),
          bark,
        );
        tw.castShadow = true;
        canopy.add(tw);
        tips.push(twTip);
      }
    }

    // Cluster centers sit along the outer third of branches, with intentional gaps
    const centers: Vector3[] = [];
    for (let i = 0; i < tips.length; i++) {
      if (opts.role !== 'mid' && r() < 0.14) continue; // leave some twigs bare for sky gaps
      const t = tips[i]!;
      centers.push(t);
      if (r() > 0.45) centers.push(t.clone().lerp(top, 0.28).add(new Vector3(0, 0.25, 0)));
    }
    // A lighter crown, not a solid cap
    if (r() > 0.2) centers.push(top.clone().add(new Vector3(0.15, 1.55, 0.1)));

    const petalGeo = new PlaneGeometry(0.28, 0.34);
    const flowerGeo = new PlaneGeometry(0.48, 0.48);
    const isFar = opts.role === 'far';
    const petalMat = isFar ? this.blossomFarMat : this.blossomMat;
    const petalsPer = opts.role === 'frame' ? 52 : opts.role === 'mid' ? 44 : 22;
    const petalCount = centers.length * petalsPer;
    const petals = new InstancedMesh(petalGeo, petalMat, petalCount);
    const flowers = new InstancedMesh(
      flowerGeo,
      this.flowerMat,
      Math.max(8, Math.floor(centers.length * (isFar ? 2.2 : 1.4))),
    );
    const o = new Object3D();
    const tint = new Color();
    let pi = 0;
    for (const c of centers) {
      for (let k = 0; k < petalsPer; k++) {
        if (r() < (opts.role === 'mid' ? 0.12 : 0.18)) continue; // holes inside the cluster
        const dir = new Vector3(r() - 0.5, (r() - 0.25) * 0.95, r() - 0.5).normalize();
        const d = 0.15 + r() * 0.7;
        o.position.copy(c).addScaledVector(dir, d);
        o.lookAt(c.clone().add(dir));
        o.rotateZ(r() * Math.PI * 2);
        o.rotateX((r() - 0.5) * 0.8);
        const sc = 0.55 + r() * 0.85;
        o.scale.set(sc, sc, sc);
        o.updateMatrix();
        if (pi < petalCount) {
          petals.setMatrixAt(pi, o.matrix);
          tint.setHSL(0.96 + r() * 0.03, 0.28 + r() * 0.28, 0.78 + r() * 0.16);
          if (isFar) tint.offsetHSL(0, -0.08, -0.04);
          petals.setColorAt(pi, tint);
          pi++;
        }
      }
    }
    petals.count = pi;
    petals.instanceMatrix.needsUpdate = true;
    petals.castShadow = opts.role === 'frame';
    canopy.add(petals);

    let fi = 0;
    for (const c of centers) {
      const n = isFar ? 2 : 1 + (r() > 0.55 ? 1 : 0);
      for (let k = 0; k < n && fi < flowers.count; k++) {
        const dir = new Vector3(r() - 0.5, r() * 0.7, r() - 0.5).normalize();
        o.position.copy(c).addScaledVector(dir, 0.35 + r() * 0.45);
        o.lookAt(c.clone().add(dir).add(new Vector3(0, 0.2, 0)));
        o.rotateZ(r() * Math.PI);
        const sc = 0.7 + r() * 0.7;
        o.scale.setScalar(sc);
        o.updateMatrix();
        flowers.setMatrixAt(fi, o.matrix);
        tint.setHSL(0.96, 0.32 + r() * 0.2, 0.8 + r() * 0.12);
        flowers.setColorAt(fi, tint);
        fi++;
      }
    }
    flowers.count = fi;
    flowers.instanceMatrix.needsUpdate = true;
    canopy.add(flowers);

    const carpet = new Mesh(
      new PlaneGeometry(opts.role === 'frame' ? 6.2 : 5.0, opts.role === 'frame' ? 6.2 : 5.0),
      new MeshStandardMaterial({
        map: petalCarpet(seed),
        transparent: true,
        depthWrite: false,
        roughness: 0.9,
      }),
    );
    carpet.rotation.x = -Math.PI / 2;
    carpet.position.y = 0.02;
    tree.add(carpet);

    this.group.add(tree);
    this.trees.push({ canopy, seed });
  }

  // ------------------------------------------------ utility pole + lamp
  private buildPoleAndLamp(): void {
    const conc = new MeshStandardMaterial({ color: 0x8a8680, roughness: 0.85 });
    const rust = new MeshStandardMaterial({ color: 0x4a3a32, roughness: 0.55, metalness: 0.25 });
    const pole = new Mesh(new CylinderGeometry(0.07, 0.1, 6.4, 10), conc);
    pole.position.set(-16.2, 3.2, -5.4);
    pole.castShadow = true;
    this.group.add(pole);
    const arm = new Mesh(new BoxGeometry(1.5, 0.05, 0.07), rust);
    arm.position.set(-16.2, 5.9, -5.4);
    arm.rotation.y = 0.5;
    this.group.add(arm);

    const metal = new MeshStandardMaterial({ color: 0x6a6e74, roughness: 0.5, metalness: 0.45 });
    const lp = new Mesh(new CylinderGeometry(0.035, 0.05, 3.4, 10), metal);
    lp.position.set(-9.6, 1.7, 3.4);
    lp.castShadow = true;
    this.group.add(lp);
    const lampArm = new Mesh(new BoxGeometry(0.04, 0.04, 0.4), metal);
    lampArm.position.set(-9.6, 3.4, 3.22);
    this.group.add(lampArm);
    const head = new Mesh(new BoxGeometry(0.18, 0.055, 0.12), this.lampHead);
    head.position.set(-9.6, 3.34, 3.05);
    this.group.add(head);
  }

  // ---------------------------------------------------------------- petals
  private buildPetals(count: number): { points: Points; vel: Float32Array } {
    const b = this.petalBounds;
    const r = rng(5);
    const pos = new Float32Array(count * 3);
    const vel = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = b.minX + r() * (b.maxX - b.minX);
      pos[i * 3 + 1] = b.minY + r() * (b.maxY - b.minY);
      pos[i * 3 + 2] = b.minZ + r() * (b.maxZ - b.minZ);
      vel[i * 3] = 0.12 + r() * 0.22;
      vel[i * 3 + 1] = -(0.22 + r() * 0.32);
      vel[i * 3 + 2] = (r() - 0.5) * 0.18;
    }
    const geo = new BufferGeometry();
    const attr = new BufferAttribute(pos, 3);
    attr.setUsage(DynamicDrawUsage);
    geo.setAttribute('position', attr);
    const mat = new PointsMaterial({
      map: petalSprite(),
      color: 0xf8dde4,
      size: 0.08,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.82,
      depthWrite: false,
    });
    const points = new Points(geo, mat);
    points.frustumCulled = false;
    return { points, vel };
  }


  private tintGrass(mat: MeshStandardMaterial): void {
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.uSunDir = { value: new Vector3(-0.6, 0.28, -0.7) };
      shader.uniforms.uSunColor = { value: new Color(0xffc888) };
      this.petalSun.push(shader.uniforms as unknown as PetalSunUniforms);
      shader.vertexShader =
        'varying vec3 vGrassWorld;\n' +
        shader.vertexShader.replace(
          '#include <project_vertex>',
          `vGrassWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
#include <project_vertex>`,
        );
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>
varying vec3 vGrassWorld;
uniform vec3 uSunDir;
uniform vec3 uSunColor;`,
        )
        .replace(
          '#include <opaque_fragment>',
          `
          float dist = length(vGrassWorld.xz);
          float cool = smoothstep(18.0, 80.0, dist);
          outgoingLight = mix(outgoingLight, outgoingLight * vec3(0.78, 0.84, 0.95), cool * 0.55);
          vec3 nrm = normalize(normal);
          vec3 sunL = normalize(uSunDir);
          float graz = pow(1.0 - max(0.0, nrm.y), 2.5) * pow(max(0.0, dot(nrm, sunL)), 1.1);
          outgoingLight += uSunColor * graz * 0.16;
          #include <opaque_fragment>
          `,
        );
    };
  }

  parkForHeroStill(): void {
    this.stillMode = true;
    this.train.position.x = STILL_TRAIN_X;
  }

  setEnvMap(envMap: Texture | null): void {
    for (const mat of [this.trainBodyMat, this.trainWinGlass, this.trainRoofMat, this.railSteel]) {
      mat.envMap = envMap;
      mat.needsUpdate = true;
    }
  }

  // ---------------------------------------------------------------- update
  applyEnvironment(u: EnvUniformSnapshot, time: number, dt: number): void {
    this.blossomMat.emissiveIntensity = 0.02 + u.twilight * 0.05 + u.nightFactor * 0.02;
    this.blossomFarMat.emissiveIntensity = 0.01 + u.twilight * 0.025;
    this.flowerMat.emissiveIntensity = 0.02 + u.twilight * 0.04;
    this.trainWinInner.emissiveIntensity = 1.7 + u.nightFactor * 0.8 + u.twilight * 0.55;
    this.lampHead.emissiveIntensity = 0.7 * u.streetLampBoost;
    const fogCol = new Color().setRGB(u.fogColor[0], u.fogColor[1], u.fogColor[2]);
    // Keep the body a cool steel grey — light fog lift, not a washed white slab
    this.trainBodyMat.color.set(0x5a616a).lerp(fogCol, 0.1);
    this.trainBodyMat.envMapIntensity = 1.7;
    this.trainRoofMat.color.set(0x3e444c).lerp(fogCol, 0.14);
    this.trainWinGlass.color.set(0x121c28);
    this.trainWinGlass.opacity = 0.2;
    this.trainWinGlass.envMapIntensity = 4.2;
    const skyHor = this.trainWinGlass.userData.uSkyHor as { value: Color } | undefined;
    const skyZen = this.trainWinGlass.userData.uSkyZen as { value: Color } | undefined;
    if (skyHor) skyHor.value.setRGB(u.skyHorizon[0], u.skyHorizon[1], u.skyHorizon[2]);
    if (skyZen) skyZen.value.setRGB(u.skyZenith[0], u.skyZenith[1], u.skyZenith[2]);
    this.trainWinGlass.envMapIntensity = 3.4;
    this.railSteel.envMapIntensity = 1.55;

    const sun = new Vector3(u.sunDir[0], u.sunDir[1], u.sunDir[2]);
    const sunCol = new Color().setRGB(u.sunColor[0], u.sunColor[1], u.sunColor[2]);
    for (const s of this.petalSun) {
      s.uSunDir.value.copy(sun);
      s.uSunColor.value.copy(sunCol);
    }

    const gust = 0.6 + 0.4 * Math.sin(time * 0.23);
    for (const t of this.trees) {
      t.canopy.rotation.z = Math.sin(time * 0.7 + t.seed) * 0.012 * gust;
      t.canopy.rotation.x = Math.cos(time * 0.55 + t.seed * 1.3) * 0.008 * gust;
    }

    if (!this.stillMode) {
      const span = 280;
      const speed = 4.6;
      this.train.position.x = ((((14 + time * speed) + 140) % span) + span) % span - 140;
    } else {
      this.train.position.x = STILL_TRAIN_X;
    }

    const step = Math.min(dt, 0.05);
    if (step > 0) {
      const attr = this.petals.geometry.getAttribute('position') as BufferAttribute;
      const arr = attr.array as Float32Array;
      const b = this.petalBounds;
      const wind = 0.6 + 0.4 * Math.sin(time * 0.31);
      for (let i = 0; i < arr.length; i += 3) {
        arr[i] = arr[i]! + this.petalVel[i]! * wind * step + Math.sin(time * 1.3 + i) * 0.004;
        arr[i + 1] = arr[i + 1]! + this.petalVel[i + 1]! * step * (1 + u.wetness * 0.6);
        arr[i + 2] = arr[i + 2]! + this.petalVel[i + 2]! * step;
        if (arr[i + 1]! < b.minY || arr[i]! > b.maxX + 3) {
          arr[i] = b.minX + Math.abs(Math.sin(i * 12.9898 + time)) * (b.maxX - b.minX);
          arr[i + 1] = b.maxY - Math.abs(Math.sin(i * 4.1 + time)) * 1.5;
          arr[i + 2] = b.minZ + Math.abs(Math.sin(i * 78.233 + time)) * (b.maxZ - b.minZ);
        }
      }
      attr.needsUpdate = true;
    }
  }

  dispose(): void {
    this.group.traverse((o) => {
      if (o instanceof Mesh || o instanceof Points || o instanceof InstancedMesh) {
        o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) m.dispose();
      }
    });
  }
}

function bodyStreakTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 64;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.fillStyle = '#8a9098';
  g.fillRect(0, 0, 256, 64);
  for (let i = 0; i < 80; i++) {
    const y = (i / 80) * 64;
    const v = 120 + ((i * 17) % 40);
    g.fillStyle = `rgba(${v},${v + 4},${v + 8},${0.18 + (i % 5) * 0.05})`;
    g.fillRect(0, y, 256, 1 + (i % 3));
  }
  g.fillStyle = 'rgba(20,24,28,0.28)';
  g.fillRect(0, 20, 256, 3);
  g.fillRect(0, 48, 256, 2);
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.repeat.set(4, 2);
  tex.anisotropy = 4;
  return tex;
}

function sleeperTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 64;
  c.height = 256;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.fillStyle = '#1c1814';
  g.fillRect(0, 0, 64, 256);
  for (let y = 0; y < 256; y++) {
    const v = 28 + ((y * 13) % 16);
    g.fillStyle = `rgb(${v + 10},${v},${v - 6})`;
    g.fillRect(0, y, 64, 1);
  }
  g.fillStyle = 'rgba(12,10,8,0.55)';
  g.fillRect(0, 0, 8, 256);
  g.fillRect(56, 0, 8, 256);
  g.fillStyle = 'rgba(90,78,64,0.35)';
  g.fillRect(10, 0, 2, 256);
  g.fillRect(44, 0, 2, 256);
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function ballastTexture(): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 128;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  g.fillStyle = '#6a665e';
  g.fillRect(0, 0, 128, 128);
  const r = rng(19);
  for (let i = 0; i < 2800; i++) {
    const v = r();
    g.fillStyle =
      v < 0.35 ? `rgba(32,30,26,${0.5 + r() * 0.45})` : v < 0.7 ? `rgba(110,104,94,${0.4 + r() * 0.4})` : `rgba(170,162,148,${0.4 + r() * 0.4})`;
    g.fillRect(r() * 128, r() * 128, 1.4 + r() * 3.0, 1.2 + r() * 2.6);
  }
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.repeat.set(80, 3);
  tex.anisotropy = 8;
  return tex;
}


function petalCarpet(seed: number): CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 256;
  const g = c.getContext('2d');
  if (!g) throw new Error('2d context');
  const r = rng(seed * 7 + 3);
  for (let i = 0; i < 700; i++) {
    const a = r() * Math.PI * 2;
    const d = Math.pow(r(), 0.7) * 120;
    const x = 128 + Math.cos(a) * d;
    const y = 128 + Math.sin(a) * d;
    const alpha = 0.75 * (1 - d / 128);
    g.fillStyle = `rgba(${240 + r() * 15},${200 + r() * 30},${210 + r() * 25},${alpha})`;
    g.beginPath();
    g.ellipse(x, y, 1.5 + r() * 1.5, 1 + r(), r() * Math.PI, 0, Math.PI * 2);
    g.fill();
  }
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  return t;
}

function sagWire(
  a: Vector3,
  b: Vector3,
  sag: number,
  mat: MeshStandardMaterial,
  radius: number,
): Mesh {
  const pts: Vector3[] = [];
  for (let i = 0; i <= 16; i++) {
    const t = i / 16;
    const p = a.clone().lerp(b, t);
    p.y -= sag * 4 * t * (1 - t);
    pts.push(p);
  }
  return new Mesh(new TubeGeometry(new CatmullRomCurve3(pts), 16, radius, 4, false), mat);
}

