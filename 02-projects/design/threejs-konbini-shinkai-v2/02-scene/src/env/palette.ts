/** DESIGN v2 成片色板 — linear-ready sRGB hex */
export const Hex = {
  amberKey: 0xe8a05a,
  sakuraBelt: 0xf0b0c0,
  warmPaper: 0xf5f0e6,
  deepIndigo: 0x0e1a32,
  airPurple: 0x6b7ba8,
  coolShadow: 0x243848,
  fridgeCyan: 0x6ec4c0,
  wetBlack: 0x12151a,
  signRed: 0xb83232,
  facadeWarm: 0xd8d2c8,
} as const;

/** sRGB hex → approximate linear RGB */
export function hexToLin(hex: number): [number, number, number] {
  const r = ((hex >> 16) & 255) / 255;
  const g = ((hex >> 8) & 255) / 255;
  const b = (hex & 255) / 255;
  const toLin = (c: number) =>
    c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  return [toLin(r), toLin(g), toLin(b)];
}
