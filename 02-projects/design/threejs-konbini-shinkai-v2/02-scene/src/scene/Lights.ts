import {
  AmbientLight,
  DirectionalLight,
  FogExp2,
  Group,
  HemisphereLight,
  PCFSoftShadowMap,
  PointLight,
  RectAreaLight,
  type Scene,
  type WebGLRenderer,
} from 'three';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';

/**
 * Layered lighting: sky hemi, amber key, awning/sign warm, fridge cyan,
 * street lamp, interior soffits, neighbor warmth.
 */
export class Lights {
  readonly group = new Group();

  private hemi: HemisphereLight;
  private amb: AmbientLight;
  private sun: DirectionalLight;
  private fill: DirectionalLight;
  private ceiling: PointLight[] = [];
  private fridge: RectAreaLight;
  private awning: RectAreaLight;
  private sign: PointLight;
  private street: PointLight;
  private vendor: PointLight;
  private neighbor: PointLight;
  private entry: PointLight;
  private windowFill: RectAreaLight;
  private checkoutWarm: PointLight;
  private ceilingZ: number[] = [];
  private fog: FogExp2 | null = null;

  constructor() {
    RectAreaLightUniformsLib.init();
    this.group.name = 'lights';

    this.hemi = new HemisphereLight(Hex.deepIndigo, Hex.wetBlack, 0.4);
    this.group.add(this.hemi);

    this.amb = new AmbientLight(Hex.warmPaper, 0.08);
    this.group.add(this.amb);

    this.sun = new DirectionalLight(Hex.amberKey, 0.9);
    this.sun.position.set(-10, 6, 12);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.camera.near = 2;
    this.sun.shadow.camera.far = 90;
    this.sun.shadow.camera.left = -28;
    this.sun.shadow.camera.right = 28;
    this.sun.shadow.camera.top = 22;
    this.sun.shadow.camera.bottom = -16;
    this.sun.shadow.bias = -0.00035;
    this.sun.shadow.normalBias = 0.03;
    this.group.add(this.sun);
    this.sun.target.position.set(0, 1.6, 0);
    this.group.add(this.sun.target);

    this.fill = new DirectionalLight(Hex.airPurple, 0.14);
    this.fill.position.set(8, 6, -4);
    this.group.add(this.fill);

    for (const z of [-1.6, -3.4, -5.2]) {
      for (const x of [-2.6, 0, 2.6]) {
        const col = z < -4.5 ? 0xc8e6ea : z > -2.2 ? 0xffe6c4 : 0xf0f3f7;
        const p = new PointLight(col, 2.2, 7.2, 1.7);
        p.position.set(x, 2.55, z);
        this.group.add(p);
        this.ceiling.push(p);
        this.ceilingZ.push(z);
      }
    }

    this.windowFill = new RectAreaLight(0xfff2e4, 4.6, 8.2, 1.8);
    this.windowFill.position.set(0, 1.45, -1.05);
    this.windowFill.lookAt(0, 1.2, 4);
    this.group.add(this.windowFill);

    this.checkoutWarm = new PointLight(0xffd4a0, 2.4, 5.2, 1.7);
    this.checkoutWarm.position.set(0.95, 2.05, -1.15);
    this.group.add(this.checkoutWarm);

    this.fridge = new RectAreaLight(Hex.fridgeCyan, 5.5, 6.4, 0.5);
    this.fridge.position.set(0, 1.15, -6.7);
    this.fridge.lookAt(0, 1.15, 0);
    this.group.add(this.fridge);

    this.awning = new RectAreaLight(Hex.warmPaper, 6, 8.6, 1.1);
    this.awning.position.set(0, 2.55, 0.95);
    this.awning.lookAt(0, 0.4, 1.6);
    this.group.add(this.awning);

    this.sign = new PointLight(Hex.warmPaper, 1.4, 8, 1.8);
    this.sign.position.set(0, 3.2, 0.8);
    this.group.add(this.sign);

    this.street = new PointLight(Hex.amberKey, 2.2, 12, 1.8);
    this.street.position.set(11.2, 3.85, 8.4);
    this.street.castShadow = false;
    this.group.add(this.street);

    this.vendor = new PointLight(Hex.fridgeCyan, 0.7, 4, 2);
    this.vendor.position.set(-4.55, 1.85, 1.35);
    this.group.add(this.vendor);

    this.entry = new PointLight(0xffe2b0, 2.4, 6.5, 1.6);
    this.entry.position.set(0, 2.15, 1.15);
    this.group.add(this.entry);

    this.neighbor = new PointLight(0xffc878, 1.6, 8, 1.8);
    // v2: re-used as the small street lamp lighting the near sakura
    this.neighbor.position.set(-9.6, 3.34, 3.05);
    this.group.add(this.neighbor);
  }

  enableShadows(renderer: WebGLRenderer): void {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = PCFSoftShadowMap;
  }

  attachFog(scene: Scene): void {
    this.fog = new FogExp2(Hex.airPurple, 0.02);
    scene.fog = this.fog;
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    this.hemi.color.setRGB(u.hemiSky[0], u.hemiSky[1], u.hemiSky[2]);
    this.hemi.groundColor.setRGB(u.hemiGround[0], u.hemiGround[1], u.hemiGround[2]);
    this.hemi.intensity = u.hemiIntensity;

    this.amb.intensity = u.ambientIntensity;

    this.sun.color.setRGB(u.sunColor[0], u.sunColor[1], u.sunColor[2]);
    this.sun.intensity = u.sunIntensity * (1 + u.twilight * 0.35);
    this.sun.position.set(
      u.sunDir[0] * 48,
      Math.max(u.sunDir[1] * 48, 4.0),
      u.sunDir[2] * 48,
    );
    this.sun.target.position.set(0, 1.8, -1);
    this.sun.target.updateMatrixWorld();

    this.fill.intensity = u.fillIntensity;

    for (let i = 0; i < this.ceiling.length; i++) {
      const z = this.ceilingZ[i] ?? -3.4;
      const k = z < -4.5 ? 2.35 : z > -2.2 ? 2.15 : 1.85;
      this.ceiling[i]!.intensity = k * u.interiorBoost;
    }

    this.windowFill.intensity = 3.8 * u.interiorBoost;
    this.checkoutWarm.intensity = 2.2 + u.interiorBoost * 0.9;
    this.fridge.intensity = 8.2 * u.emissiveBoost * 0.9;
    this.awning.intensity = 6.2 + u.interiorBoost * 2.6;
    this.sign.intensity = 2.5 + u.emissiveBoost * 1.25;
    this.street.intensity = 0.7 * u.streetLampBoost;
    this.vendor.intensity = 0.4 + u.emissiveBoost * 0.3;
    this.neighbor.intensity = 0.35 + u.nightFactor * 0.5 + u.twilight * 0.15;
    this.entry.intensity = 1.55 + u.interiorBoost * 1.0 + u.twilight * 0.35;

    if (this.fog) {
      this.fog.density = u.fogDensity;
      this.fog.color.setRGB(u.fogColor[0], u.fogColor[1], u.fogColor[2]);
    }
  }

  dispose(): void {
    this.group.clear();
    this.ceiling = [];
  }
}
