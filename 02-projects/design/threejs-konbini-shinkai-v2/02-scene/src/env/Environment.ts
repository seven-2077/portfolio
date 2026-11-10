import { Hex, hexToLin } from './palette';

/** Unified environment state machine → GLSL / lights.
 *  Shinkai still-frame default: rainy amber dusk. Horizon keeps warmth in rain.
 */

export type Weather = 'clear' | 'overcast' | 'rain';
export type Season = 'spring' | 'summer' | 'autumn' | 'winter';

export interface EnvUniformSnapshot {
  timeOfDay: number;
  weather: Weather;
  season: Season;
  seasonT: number;
  sunDir: [number, number, number];
  sunColor: [number, number, number];
  sunIntensity: number;
  skyZenith: [number, number, number];
  skyHorizon: [number, number, number];
  fogColor: [number, number, number];
  fogDensity: number;
  wetness: number;
  emissiveBoost: number;
  hemiIntensity: number;
  hemiSky: [number, number, number];
  hemiGround: [number, number, number];
  ambientIntensity: number;
  fillIntensity: number;
  streetLampBoost: number;
  nightFactor: number;
  twilight: number;
  exposure: number;
  interiorBoost: number;
  cloudCover: number;
  godray: number;
}

const SEASON_T: Record<Season, number> = {
  spring: 0,
  summer: 0.33,
  autumn: 0.66,
  winter: 1,
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerp3(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

export class Environment {
  /** Amber rainy dusk — sky is the hero, wet asphalt reads reflections */
  timeOfDay = 0.735;
  weather: Weather = 'rain';
  season: Season = 'autumn';

  private snapshot: EnvUniformSnapshot;

  constructor() {
    this.snapshot = this.compute();
  }

  get state() {
    return {
      timeOfDay: this.timeOfDay,
      weather: this.weather,
      season: this.season,
    };
  }

  setTimeOfDay(t: number): void {
    this.timeOfDay = Math.min(1, Math.max(0, t));
  }

  setWeather(w: Weather): void {
    this.weather = w;
  }

  setSeason(s: Season): void {
    this.season = s;
  }

  update(_dt: number): EnvUniformSnapshot {
    this.snapshot = this.compute();
    return this.snapshot;
  }

  getUniforms(): EnvUniformSnapshot {
    return this.snapshot;
  }

  private compute(): EnvUniformSnapshot {
    const t = this.timeOfDay;
    const angle = (t - 0.25) * Math.PI * 2;
    const sunYRaw = Math.sin(angle);
    // Keep dusk colors from the true solar altitude, but lift the *visible* sun
    // just above the store roofline so shafts can enter the frame.
    const sunY = sunYRaw + 0.16 * smoothstep(-0.2, 0.15, sunYRaw) * (1 - smoothstep(0.25, 0.55, sunYRaw));
    const sunX = Math.cos(angle) * 0.55 - 0.22;
    const sunZ = -Math.max(0.42, Math.abs(Math.cos(angle)) * 0.78);
    const len = Math.hypot(sunX, Math.max(sunY, -0.05), sunZ) || 1;
    const sunDir: [number, number, number] = [sunX / len, Math.max(sunY, -0.05) / len, sunZ / len];

    const day = smoothstep(-0.12, 0.28, sunYRaw);
    const nightFactor = 1 - day;
    const twilight =
      smoothstep(-0.32, 0.04, sunYRaw) * (1 - smoothstep(0.05, 0.42, sunYRaw));

    const wClear = this.weather === 'clear' ? 1 : 0;
    const wOver = this.weather === 'overcast' ? 1 : 0;
    const wRain = this.weather === 'rain' ? 1 : 0;
    const seasonT = SEASON_T[this.season];
    const cloudCover = wClear * 0.22 + wOver * 0.72 + wRain * 0.82;

    const amber = hexToLin(Hex.amberKey);
    const sakura = hexToLin(Hex.sakuraBelt);
    const skyDayZ = hexToLin(0x4a7ab8);
    const skyDayH = hexToLin(0xcdd8ec);
    const skyNightZ = hexToLin(Hex.deepIndigo);
    const skyNightH = hexToLin(0x1a2848);
    const airPurple = hexToLin(Hex.airPurple);
    const coolShadow = hexToLin(Hex.coolShadow);

    let zenith = lerp3(skyNightZ, skyDayZ, day);
    let horizon = lerp3(skyNightH, skyDayH, day);
    // Keep amber / sakura belt even in rain — this is the still-frame hero
    horizon = lerp3(horizon, amber, twilight * 0.82);
    horizon = lerp3(horizon, sakura, twilight * 0.28 * (1 - nightFactor * 0.35));

    if (this.season === 'spring') {
      horizon = lerp3(horizon, sakura, 0.1 * (twilight + day * 0.15));
    } else if (this.season === 'summer') {
      zenith = lerp3(zenith, hexToLin(0x3a6aa8), 0.18 * day);
    } else if (this.season === 'autumn') {
      horizon = lerp3(horizon, amber, 0.12 * (day * 0.4 + twilight));
    } else {
      zenith = lerp3(zenith, coolShadow, 0.18);
    }

    // Rain darkens zenith / adds storm weight, but does NOT grey the amber horizon
    const stormZ: [number, number, number] = lerp3(zenith, coolShadow, 0.28);
    zenith = lerp3(zenith, stormZ, (wOver * 0.35 + wRain * 0.4) * (1 - twilight * 0.5));
    horizon = lerp3(horizon, airPurple, (wOver * 0.1 + wRain * 0.08) * (1 - twilight * 0.85));

    const sunNoon = hexToLin(0xfff1dc);
    let sunColor = lerp3(amber, sunNoon, smoothstep(0.05, 0.45, sunY));
    sunColor = lerp3(sunColor, amber, twilight * 0.7);
    sunColor = lerp3(sunColor, [0.16, 0.2, 0.36], nightFactor * 0.8);

    const clearSun = Math.max(0, sunYRaw) * 1.15 + twilight * 1.15;
    // Rain dusk still carries a real amber key so shafts have something to light.
    const sunIntensity =
      clearSun * (wClear * 1.12 + wOver * 0.58 + wRain * 0.72) + nightFactor * 0.02;

    const fogDensity =
      0.009 * wClear + 0.015 * wOver + 0.018 * wRain + nightFactor * 0.003 + twilight * 0.002;

    // Cool blue-grey veil — don't wash the whole frame pink-orange.
    const fogColor = lerp3(
      lerp3(coolShadow, airPurple, 0.7),
      airPurple,
      0.35 + wRain * 0.25 + wOver * 0.15,
    );

    // Residual wet streets at dusk even if not raining hard: rain = 1, overcast damp
    const wetness = wClear * 0.08 + wOver * 0.45 + wRain * 1.0;
    const emissiveBoost = lerp(0.55, 1.75, nightFactor) + wRain * 0.18 + twilight * 0.2;

    const hemiIntensity =
      lerp(0.1, 0.4, day) * (1 - cloudCover * 0.4) + twilight * 0.07;
    const hemiSky = zenith;
    const hemiGround: [number, number, number] = lerp3(
      hexToLin(Hex.wetBlack),
      hexToLin(Hex.coolShadow),
      day * 0.45,
    );

    const ambientIntensity = lerp(0.03, 0.08, day);
    const fillIntensity = lerp(0.05, 0.16, day) * (1 - wRain * 0.25);
    const streetLampBoost = lerp(0.35, 1.15, nightFactor) + wRain * 0.18 + twilight * 0.12;
    const interiorBoost = lerp(0.95, 1.45, nightFactor) + twilight * 0.28;
    const exposure = lerp(1.08, 0.92, nightFactor) - wRain * 0.04 + twilight * 0.03;
    const godray = twilight * (0.7 + wClear * 0.3 + wRain * 0.25) * (1 - nightFactor * 0.4);

    return {
      timeOfDay: t,
      weather: this.weather,
      season: this.season,
      seasonT,
      sunDir,
      sunColor,
      sunIntensity,
      skyZenith: zenith,
      skyHorizon: horizon,
      fogColor,
      fogDensity,
      wetness,
      emissiveBoost,
      hemiIntensity,
      hemiSky,
      hemiGround,
      ambientIntensity,
      fillIntensity,
      streetLampBoost,
      nightFactor,
      twilight,
      exposure,
      interiorBoost,
      cloudCover,
      godray,
    };
  }
}
