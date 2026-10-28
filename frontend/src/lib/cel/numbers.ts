// format_number(): the browser's copy of backend/app/cel/numbers.py. Rounding starts
// from the number as it's written (the shortest text that reads back as the same
// double, which JavaScript and Python agree on), and halves round away from zero.

export const MAX_DECIMALS = 10;

/** A number's digits as text: whole part and fraction, without a sign. */
function digitsOf(value: number | bigint): { negative: boolean; whole: string; fraction: string } {
  if (typeof value === "bigint") {
    return { negative: value < 0n, whole: (value < 0n ? -value : value).toString(), fraction: "" };
  }
  const [mantissa, exponentText] = String(Math.abs(value)).split("e");
  const exponent = exponentText ? Number(exponentText) : 0;
  const [whole, fraction = ""] = mantissa.split(".");
  const digits = whole + fraction;
  const point = whole.length + exponent;
  if (point <= 0) return { negative: value < 0, whole: "0", fraction: "0".repeat(-point) + digits };
  if (point >= digits.length) return { negative: value < 0, whole: digits + "0".repeat(point - digits.length), fraction: "" };
  return { negative: value < 0, whole: digits.slice(0, point), fraction: digits.slice(point) };
}

export function formatNumber(value: number | bigint, decimals: number, decimalMark: string, groupMark: string): string {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > MAX_DECIMALS) {
    throw new Error(`format_number() takes 0 to ${MAX_DECIMALS} decimals.`);
  }
  if (typeof value === "number" && !Number.isFinite(value)) throw new Error("format_number() needs a finite number.");
  const { negative, whole, fraction } = digitsOf(value);
  const padded = fraction.padEnd(decimals + 1, "0");
  let scaled = BigInt(whole + padded.slice(0, decimals));
  if (padded[decimals] >= "5") scaled += 1n;
  const text = scaled.toString().padStart(decimals + 1, "0");
  let wholeOut = decimals ? text.slice(0, -decimals) : text;
  const groups: string[] = [];
  while (wholeOut.length > 3) {
    groups.unshift(wholeOut.slice(-3));
    wholeOut = wholeOut.slice(0, -3);
  }
  groups.unshift(wholeOut);
  const out = groups.join(groupMark) + (decimals ? decimalMark + text.slice(-decimals) : "");
  // A number that rounds to zero is written without a minus sign.
  return negative && scaled !== 0n ? "-" + out : out;
}
