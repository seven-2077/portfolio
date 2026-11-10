import {
  AdditiveBlending,
  BoxGeometry,
  Color,
  CylinderGeometry,
  Group,
  Mesh,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  ShaderMaterial,
  type Texture,
} from 'three';
import type { EnvUniformSnapshot } from '../env/Environment';
import { Hex } from '../env/palette';
import {
  makeDoorDecal,
  makeFacadeTiles,
  makeGlassDroplets,
  makeHoursPoster,
  makeKickplate,
  makePoster,
  makeSign,
  makeSignEmissive,
  makeSoffit,
} from '../textures/makeTextures';

const W = 9.2;
const H = 2.72;

/** Storefront: tile walls, thick awning, lightbox sign, mullioned glass, auto doors. */
export class Facade {
  readonly group = new Group();
  readonly glassMeshes: Mesh[] = [];
  readonly signMap: Texture;
  private signMat!: MeshStandardMaterial;
  private soffitMat!: MeshStandardMaterial;
  private fasciaMat!: MeshStandardMaterial;
  private innerGlass!: MeshPhysicalMaterial;
  private outerGlass!: MeshPhysicalMaterial;
  private skyFilm!: ShaderMaterial;

  constructor() {
    this.group.name = 'facade';

    const tiles = makeFacadeTiles();
    const wallMat = new MeshStandardMaterial({
      map: tiles,
      color: Hex.facadeWarm,
      roughness: 0.78,
      metalness: 0.04,
    });
    const darkMetal = new MeshStandardMaterial({
      color: 0x1c2024,
      roughness: 0.28,
      metalness: 0.82,
    });
    const brushed = new MeshStandardMaterial({
      color: 0x6a7076,
      roughness: 0.28,
      metalness: 0.72,
    });

    const left = new Mesh(new BoxGeometry(0.28, H + 0.9, 7.4), wallMat);
    left.position.set(-W * 0.5 - 0.05, (H + 0.9) * 0.5, -3.5);
    left.castShadow = true;
    left.receiveShadow = true;
    this.group.add(left);
    const right = new Mesh(new BoxGeometry(0.28, H + 0.9, 7.4), wallMat);
    right.position.set(W * 0.5 + 0.05, (H + 0.9) * 0.5, -3.5);
    right.castShadow = true;
    this.group.add(right);
    const back = new Mesh(new BoxGeometry(W + 0.5, H + 0.9, 0.3), wallMat);
    back.position.set(0, (H + 0.9) * 0.5, -7.25);
    this.group.add(back);

    const parapet = new Mesh(new BoxGeometry(W + 0.55, 0.95, 0.45), wallMat);
    parapet.position.set(0, H + 0.48, 0.05);
    parapet.castShadow = true;
    parapet.receiveShadow = true;
    this.group.add(parapet);

    const cornice = new Mesh(new BoxGeometry(W + 0.75, 0.1, 0.62), brushed);
    cornice.position.set(0, H + 0.98, 0.12);
    this.group.add(cornice);

    this.buildLightbox(darkMetal);
    this.signMap = this.signMat.map as Texture;

    this.buildAwning();
    this.buildGlazing(darkMetal, brushed);
    this.buildDoors(darkMetal, brushed);
    this.buildPosters();
    this.buildServiceClutter(wallMat, darkMetal);
  }

  private buildLightbox(darkMetal: MeshStandardMaterial): void {
    const signMap = makeSign();
    const signEmit = makeSignEmissive();

    const y = H + 0.42;
    // Open aluminum can: back + four sides, front left open for the lit face
    const back = new Mesh(new BoxGeometry(W - 0.28, 0.86, 0.08), darkMetal);
    back.position.set(0, y, 0.2);
    this.group.add(back);
    const topF = new Mesh(new BoxGeometry(W - 0.28, 0.08, 0.46), darkMetal);
    topF.position.set(0, y + 0.43, 0.4);
    this.group.add(topF);
    const botF = new Mesh(new BoxGeometry(W - 0.28, 0.08, 0.46), darkMetal);
    botF.position.set(0, y - 0.43, 0.4);
    this.group.add(botF);
    const sideL = new Mesh(new BoxGeometry(0.1, 0.86, 0.46), darkMetal);
    sideL.position.set(-(W - 0.28) * 0.5, y, 0.4);
    this.group.add(sideL);
    const sideR = sideL.clone();
    sideR.position.x *= -1;
    this.group.add(sideR);

    this.fasciaMat = new MeshStandardMaterial({
      color: 0xc8c0b4,
      emissive: new Color(0x8a8074),
      emissiveIntensity: 0.35,
      roughness: 0.4,
    });
    const fascia = new Mesh(new BoxGeometry(W - 0.5, 0.7, 0.16), this.fasciaMat);
    fascia.position.set(0, y, 0.34);
    this.group.add(fascia);

    this.signMat = new MeshStandardMaterial({
      map: signMap,
      color: 0xffffff,
      emissive: new Color(0xffffff),
      emissiveMap: signEmit,
      emissiveIntensity: 1.85,
      roughness: 0.28,
    });
    const sign = new Mesh(new PlaneGeometry(W - 0.58, 0.62), this.signMat);
    sign.position.set(0, y, 0.44);
    this.group.add(sign);

    const red = new MeshStandardMaterial({
      color: Hex.signRed,
      emissive: new Color(Hex.signRed),
      emissiveIntensity: 0.55,
      roughness: 0.4,
    });
    const capL = new Mesh(new BoxGeometry(0.12, 0.82, 0.48), red);
    capL.position.set(-(W - 0.36) * 0.5, y, 0.4);
    this.group.add(capL);
    const capR = capL.clone();
    capR.position.x *= -1;
    this.group.add(capR);
    const strip = new Mesh(new BoxGeometry(W - 0.36, 0.05, 0.48), red);
    strip.position.set(0, y + 0.4, 0.4);
    this.group.add(strip);
  }

  private buildAwning(): void {
    const shell = new MeshStandardMaterial({
      color: 0xd4cec4,
      roughness: 0.5,
      metalness: 0.12,
    });
    const awning = new Mesh(new BoxGeometry(W + 0.3, 0.1, 1.55), shell);
    awning.position.set(0, H - 0.02, 0.95);
    awning.rotation.x = -0.08;
    awning.castShadow = true;
    this.group.add(awning);

    this.soffitMat = new MeshStandardMaterial({
      map: makeSoffit(),
      color: 0xfff1d4,
      emissive: new Color(0xffe2b0),
      emissiveIntensity: 0.9,
      roughness: 0.48,
    });
    const soffit = new Mesh(new BoxGeometry(W + 0.22, 0.04, 1.42), this.soffitMat);
    soffit.position.set(0, H - 0.1, 0.92);
    soffit.rotation.x = -0.08;
    this.group.add(soffit);

    const ribMat = new MeshStandardMaterial({ color: 0xc4b498, roughness: 0.48, metalness: 0.08 });
    for (let i = 0; i < 14; i++) {
      const rib = new Mesh(new BoxGeometry(0.04, 0.03, 1.4), ribMat);
      rib.position.set(-W * 0.48 + i * ((W + 0.1) / 13), H - 0.13, 0.92);
      rib.rotation.x = -0.08;
      this.group.add(rib);
    }
    const rod = new MeshStandardMaterial({
      color: 0x6a7076,
      roughness: 0.3,
      metalness: 0.7,
    });
    for (const x of [-3.6, -1.2, 1.2, 3.6]) {
      const r = new Mesh(new CylinderGeometry(0.018, 0.018, 0.85, 8), rod);
      r.position.set(x, H - 0.5, 1.45);
      r.rotation.x = 0.55;
      this.group.add(r);
    }
  }

  private makeGlassMats(): void {
    const drops = makeGlassDroplets();
    this.innerGlass = new MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0,
      roughness: 0.03,
      transmission: 0.94,
      thickness: 0.1,
      ior: 1.5,
      transparent: true,
      opacity: 1,
      envMapIntensity: 0.45,
      attenuationColor: new Color(0xf7fbff),
      attenuationDistance: 4.0,
    });
    this.outerGlass = new MeshPhysicalMaterial({
      color: 0xffffff,
      metalness: 0.08,
      roughness: 0.06,
      roughnessMap: drops,
      bumpMap: drops,
      bumpScale: 0.016,
      transparent: true,
      opacity: 0.16,
      depthWrite: false,
      envMapIntensity: 2.35,
      clearcoat: 1,
      clearcoatRoughness: 0.12,
      clearcoatRoughnessMap: drops,
    });
    // World-space fresnel + dusk sky tint: visible reflections without a grey veil
    this.outerGlass.onBeforeCompile = (shader) => {
      shader.uniforms.uSkyHor = { value: new Color(0xf4a078) };
      shader.uniforms.uSkyZen = { value: new Color(0xc45a6a) };
      this.outerGlass.userData.uSkyHor = shader.uniforms.uSkyHor;
      this.outerGlass.userData.uSkyZen = shader.uniforms.uSkyZen;
      shader.vertexShader = shader.vertexShader
        .replace(
          '#include <common>',
          '#include <common>\nvarying vec3 vGlassWorldPos;\nvarying vec3 vGlassWorldN;',
        )
        .replace(
          '#include <project_vertex>',
          '#include <project_vertex>\n' +
            'vGlassWorldPos = (modelMatrix * vec4(transformed, 1.0)).xyz;\n' +
            'vGlassWorldN = normalize((modelMatrix * vec4(objectNormal, 0.0)).xyz);',
        );
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          '#include <common>\nvarying vec3 vGlassWorldPos;\nvarying vec3 vGlassWorldN;\nuniform vec3 uSkyHor;\nuniform vec3 uSkyZen;',
        )
        .replace(
          '#include <opaque_fragment>',
          'vec3 nG = normalize(vGlassWorldN);\n' +
            'vec3 vG = normalize(cameraPosition - vGlassWorldPos);\n' +
            'float fG = pow(1.0 - clamp(dot(nG, vG), 0.0, 1.0), 1.7);\n' +
            'vec3 rG = reflect(-vG, nG);\n' +
            'vec3 skyC = mix(uSkyHor, uSkyZen, clamp(rG.y * 0.65 + 0.2, 0.0, 1.0));\n' +
            'outgoingLight += skyC * (0.22 + 0.95 * fG);\n' +
            'diffuseColor.a = clamp(mix(0.08, 0.4, fG), 0.07, 0.48);\n' +
            '#include <opaque_fragment>',
        );
    };
    this.outerGlass.customProgramCacheKey = () => 'konbini-glass-fresnel-v5b';

    this.skyFilm = new ShaderMaterial({
      uniforms: {
        uSkyHor: { value: new Color(0xf4a078) },
        uSkyZen: { value: new Color(0xd45a6a) },
      },
      vertexShader: `
        varying vec3 vWPos;
        varying vec3 vWN;
        void main() {
          vec4 wp = modelMatrix * vec4(position, 1.0);
          vWPos = wp.xyz;
          vWN = normalize(mat3(modelMatrix) * normal);
          gl_Position = projectionMatrix * viewMatrix * wp;
        }
      `,
      fragmentShader: `
        uniform vec3 uSkyHor;
        uniform vec3 uSkyZen;
        varying vec3 vWPos;
        varying vec3 vWN;
        void main() {
          vec3 n = normalize(vWN);
          vec3 v = normalize(cameraPosition - vWPos);
          float f = pow(1.0 - clamp(dot(n, v), 0.0, 1.0), 1.55);
          vec3 r = reflect(-v, n);
          vec3 sky = mix(uSkyHor, uSkyZen, clamp(r.y * 0.7 + 0.15, 0.0, 1.0));
          // Additive dusk catch: stronger at a glance, a hint even face-on
          gl_FragColor = vec4(sky * (0.16 + 0.7 * f), 1.0);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      toneMapped: true,
      fog: false,
    });
  }

  private addPane(w: number, h: number, x: number, y: number, zInner: number, name: string): void {
    const inner = new Mesh(new BoxGeometry(w, h, 0.05), this.innerGlass);
    inner.position.set(x, y, zInner);
    inner.name = name;
    this.group.add(inner);
    this.glassMeshes.push(inner);
    const outer = new Mesh(new BoxGeometry(w, h, 0.012), this.outerGlass);
    outer.position.set(x, y, zInner + 0.055);
    outer.name = name + '_film';
    this.group.add(outer);
    this.glassMeshes.push(outer);
    const sky = new Mesh(new PlaneGeometry(w, h), this.skyFilm);
    sky.position.set(x, y, zInner + 0.07);
    sky.name = name + '_sky';
    this.group.add(sky);
    this.glassMeshes.push(sky);
  }

  private buildGlazing(
    darkMetal: MeshStandardMaterial,
    brushed: MeshStandardMaterial,
  ): void {
    this.makeGlassMats();

    const kick = new Mesh(
      new BoxGeometry(W - 0.2, 0.42, 0.24),
      new MeshStandardMaterial({
        map: makeKickplate(),
        color: 0xffffff,
        roughness: 0.42,
        metalness: 0.45,
      }),
    );
    kick.position.set(0, 0.21, 0.05);
    this.group.add(kick);
    // Brushed cap on the kickplate so wall-skirt / frame / tiles stay separate
    const kickCap = new Mesh(new BoxGeometry(W - 0.18, 0.04, 0.26), brushed);
    kickCap.position.set(0, 0.43, 0.06);
    this.group.add(kickCap);

    const head = new Mesh(new BoxGeometry(W - 0.15, 0.16, 0.24), brushed);
    head.position.set(0, H - 0.28, 0.08);
    this.group.add(head);

    const paneH = H - 0.42 - 0.28;
    const paneY = 0.42 + paneH * 0.5;
    const leftW = 3.15;
    const rightW = 3.15;
    this.addPane(leftW, paneH, -W * 0.5 + 0.22 + leftW * 0.5, paneY, 0.1, 'glass_left');
    this.addPane(rightW, paneH, W * 0.5 - 0.22 - rightW * 0.5, paneY, 0.1, 'glass_right');

    const mullionsX = [-4.4, -2.85, -1.35, 1.35, 2.85, 4.4];
    for (const x of mullionsX) {
      const m = new Mesh(new BoxGeometry(0.08, paneH + 0.1, 0.16), darkMetal);
      m.position.set(x, paneY, 0.12);
      this.group.add(m);
    }
    const transom = new Mesh(new BoxGeometry(W - 0.3, 0.07, 0.14), darkMetal);
    transom.position.set(0, paneY + paneH * 0.18, 0.12);
    this.group.add(transom);

    for (const x of [-W * 0.5 + 0.08, W * 0.5 - 0.08]) {
      const p = new Mesh(new BoxGeometry(0.16, H - 0.15, 0.22), darkMetal);
      p.position.set(x, (H - 0.15) * 0.5, 0.1);
      this.group.add(p);
    }
  }

  private buildDoors(
    darkMetal: MeshStandardMaterial,
    brushed: MeshStandardMaterial,
  ): void {
    const paneH = 2.15;
    const paneY = 0.2 + paneH * 0.5;
    const doorW = 0.88;
    for (const x of [-0.82, 0.82]) {
      const stile = new BoxGeometry(0.07, paneH + 0.08, 0.14);
      const left = new Mesh(stile, darkMetal);
      left.position.set(x - doorW * 0.5, paneY, 0.16);
      this.group.add(left);
      const right = new Mesh(stile, darkMetal);
      right.position.set(x + doorW * 0.5, paneY, 0.16);
      this.group.add(right);
      const rail = new BoxGeometry(doorW + 0.07, 0.07, 0.14);
      const top = new Mesh(rail, darkMetal);
      top.position.set(x, paneY + paneH * 0.5, 0.16);
      this.group.add(top);
      const bot = new Mesh(rail, darkMetal);
      bot.position.set(x, paneY - paneH * 0.5, 0.16);
      this.group.add(bot);
      const mid = new Mesh(new BoxGeometry(doorW, 0.05, 0.12), darkMetal);
      mid.position.set(x, 1.15, 0.16);
      this.group.add(mid);
      this.addPane(doorW - 0.06, paneH - 0.1, x, paneY, 0.16, x < 0 ? 'door_L' : 'door_R');
      const h = new Mesh(new CylinderGeometry(0.012, 0.012, 0.42, 8), brushed);
      h.position.set(x + (x < 0 ? 0.34 : -0.34), 1.1, 0.28);
      this.group.add(h);
    }
    const th = new Mesh(
      new BoxGeometry(2.3, 0.06, 0.55),
      new MeshStandardMaterial({ color: 0x3a3e44, roughness: 0.35, metalness: 0.55 }),
    );
    th.position.set(0, 0.03, 0.28);
    this.group.add(th);
  }

  private buildPosters(): void {
    // Sparse, small: hours, one promo, auto-door notice. No cheap neon wall.
    const hours = new Mesh(
      new PlaneGeometry(0.28, 0.36),
      new MeshStandardMaterial({ map: makeHoursPoster(), roughness: 0.55, transparent: true }),
    );
    hours.position.set(-4.05, 1.55, 0.175);
    this.group.add(hours);

    const promo = new Mesh(
      new PlaneGeometry(0.32, 0.46),
      new MeshStandardMaterial({ map: makePoster(0), roughness: 0.55 }),
    );
    promo.position.set(3.55, 1.48, 0.175);
    this.group.add(promo);

    const door = new Mesh(
      new PlaneGeometry(0.28, 0.14),
      new MeshStandardMaterial({ map: makeDoorDecal(), roughness: 0.45, transparent: true, opacity: 0.92 }),
    );
    door.position.set(-0.55, 1.85, 0.23);
    this.group.add(door);
  }

  private buildServiceClutter(
    wallMat: MeshStandardMaterial,
    darkMetal: MeshStandardMaterial,
  ): void {
    const ac = new Mesh(
      new BoxGeometry(1.1, 0.55, 0.38),
      new MeshStandardMaterial({ color: 0xc8ccd0, roughness: 0.45, metalness: 0.25 }),
    );
    ac.position.set(W * 0.5 + 0.32, 2.15, -1.6);
    this.group.add(ac);
    const grille = new Mesh(new BoxGeometry(0.95, 0.28, 0.02), darkMetal);
    grille.position.set(W * 0.5 + 0.52, 2.15, -1.6);
    this.group.add(grille);

    const pipe = new Mesh(
      new CylinderGeometry(0.07, 0.07, 1.6, 10),
      new MeshStandardMaterial({ color: 0x6a6e72, roughness: 0.4, metalness: 0.5 }),
    );
    pipe.position.set(W * 0.5 + 0.22, 3.3, -2.4);
    this.group.add(pipe);
    const cap = new Mesh(new CylinderGeometry(0.12, 0.12, 0.05, 10), darkMetal);
    cap.position.set(W * 0.5 + 0.22, 4.12, -2.4);
    this.group.add(cap);

    const meter = new Mesh(new BoxGeometry(0.32, 0.4, 0.12), darkMetal);
    meter.position.set(-W * 0.5 - 0.22, 1.3, 0.15);
    this.group.add(meter);

    const spout = new Mesh(
      new CylinderGeometry(0.04, 0.04, 3.4, 8),
      new MeshStandardMaterial({ color: 0x7a7268, roughness: 0.5, metalness: 0.3 }),
    );
    spout.position.set(-W * 0.5 - 0.18, 1.7, 0.0);
    this.group.add(spout);

    void wallMat;
  }

  applyEnvironment(u: EnvUniformSnapshot): void {
    this.signMat.emissiveIntensity = 1.7 + u.emissiveBoost * 0.6;
    this.fasciaMat.emissiveIntensity = 0.3 + u.emissiveBoost * 0.2;
    this.soffitMat.emissiveIntensity = 0.7 + u.interiorBoost * 0.4 + u.twilight * 0.15;
    const hor = this.outerGlass.userData.uSkyHor as { value: Color } | undefined;
    const zen = this.outerGlass.userData.uSkyZen as { value: Color } | undefined;
    if (hor) hor.value.setRGB(u.skyHorizon[0], u.skyHorizon[1], u.skyHorizon[2]);
    if (zen) zen.value.setRGB(u.skyZenith[0], u.skyZenith[1], u.skyZenith[2]);
    if (this.skyFilm) {
      (this.skyFilm.uniforms.uSkyHor.value as Color).setRGB(u.skyHorizon[0], u.skyHorizon[1], u.skyHorizon[2]);
      (this.skyFilm.uniforms.uSkyZen.value as Color).setRGB(u.skyZenith[0], u.skyZenith[1], u.skyZenith[2]);
    }
  }

  setEnvMap(envMap: MeshPhysicalMaterial['envMap']): void {
    for (const m of this.glassMeshes) {
      const mat = m.material as MeshPhysicalMaterial;
      mat.envMap = envMap;
      mat.needsUpdate = true;
    }
  }

  dispose(): void {
    this.group.traverse((o) => {
      if (o instanceof Mesh) {
        o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) m.dispose();
      }
    });
  }
}
