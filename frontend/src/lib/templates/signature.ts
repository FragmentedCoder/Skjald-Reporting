// A signature drawn on a signature pad: its strokes, each a run of points (x, y, x, y
// and so on) on a sheet 600 wide and 200 high. Kept as numbers rather than a picture,
// so it prints sharp at any size and nothing but lines can be in it.

export const PAD = { width: 600, height: 200 } as const;
const MAX_STROKES = 400;
const MAX_POINTS = 4000;

export interface Drawn {
  strokes: number[][];
}

/** The strokes of a signature pad's answer, or null when it isn't signed (or isn't one). */
export function drawn(raw: unknown): number[][] | null {
  const strokes = (raw as Drawn | null | undefined)?.strokes;
  if (!Array.isArray(strokes) || !strokes.length || strokes.length > MAX_STROKES) return null;
  const sound = strokes.every((stroke) => Array.isArray(stroke) && stroke.length >= 2 && stroke.length % 2 === 0
    && stroke.length <= MAX_POINTS * 2 && stroke.every((n) => typeof n === "number" && Number.isFinite(n)));
  return sound ? (strokes as number[][]) : null;
}

/** The strokes as one SVG path; a single point is a dot. */
export function strokePath(strokes: number[][]): string {
  const at = (n: number, most: number) => String(Math.round(Math.min(Math.max(n, 0), most) * 10) / 10);
  return strokes
    .map((stroke) => {
      const points: string[] = [];
      for (let i = 0; i < stroke.length; i += 2) points.push(`${at(stroke[i], PAD.width)} ${at(stroke[i + 1], PAD.height)}`);
      return points.length === 1 ? `M${points[0]}h0.1` : `M${points.join("L")}`;
    })
    .join("");
}

/**
 * The part of the sheet the strokes are on, with a little room around, as an SVG view
 * box: a signature drawn small, or in a corner, still fills its place on the page.
 */
export function strokeBox(strokes: number[][]): string {
  let [left, top, right, bottom]: number[] = [PAD.width, PAD.height, 0, 0];
  for (const stroke of strokes) {
    for (let i = 0; i < stroke.length; i += 2) {
      left = Math.min(left, stroke[i]);
      right = Math.max(right, stroke[i]);
      top = Math.min(top, stroke[i + 1]);
      bottom = Math.max(bottom, stroke[i + 1]);
    }
  }
  const room = 6;
  const x = Math.max(0, Math.min(left, PAD.width) - room);
  const y = Math.max(0, Math.min(top, PAD.height) - room);
  const width = Math.max(room * 2, Math.min(right, PAD.width) + room - x);
  const height = Math.max(room * 2, Math.min(bottom, PAD.height) + room - y);
  return [x, y, width, height].map((n) => Math.round(n * 10) / 10).join(" ");
}
