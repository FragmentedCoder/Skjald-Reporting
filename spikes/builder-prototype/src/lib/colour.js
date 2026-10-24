// Callout tones come from the report style, so reports stay on brand and readable.
// A report designer can also pick a custom colour; the text colour is then chosen for contrast,
// and the builder warns when neither dark nor light text reaches WCAG AA (4.5:1).

export const TONES = {
  info: {label: 'Info', bg: '#DCE6EE', fg: '#234C72', border: '#B9CCDD'},
  note: {label: 'Note', bg: '#EFEFEF', fg: '#0F1B2D', border: '#D6D6D6'},
  warning: {label: 'Warning', bg: '#FBEFD9', fg: '#8A5A12', border: '#F0D7A8'},
  critical: {label: 'Critical', bg: '#F9E3E0', fg: '#A3352A', border: '#EFC2BC'},
  success: {label: 'Success', bg: '#E3F1E8', fg: '#2F6B47', border: '#BFDDCA'},
}

const INK = '#0F1B2D'
const WHITE = '#FFFFFF'

function luminance(hex) {
  const n = hex.replace('#', '')
  const full = n.length === 3 ? n.split('').map((c) => c + c).join('') : n
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

export const isHex = (value) => /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(String(value ?? ''))

// The colours a callout is drawn with, for a tone or a custom background.
export function calloutColours(block) {
  if (block.tone !== 'custom') return {...(TONES[block.tone] ?? TONES.info), ratio: null, ok: true}
  const bg = isHex(block.color) ? block.color : TONES.info.bg
  const dark = contrast(bg, INK)
  const light = contrast(bg, WHITE)
  const fg = dark >= light ? INK : WHITE
  const ratio = Math.max(dark, light)
  return {bg, fg, border: bg, ratio: Math.round(ratio * 10) / 10, ok: ratio >= 4.5}
}
