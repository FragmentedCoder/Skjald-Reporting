// Splits the layout into pages the way the PDF renderer does (docs/architecture.md, "Page breaks"):
// a section with "Start on a new page" begins a page, a page-break block forces one, and the cover is page 1.
// Very long sections still flow over more pages in the PDF; the preview flags pages that run over.
// Tables and images are numbered in reading order ("Table 1", "Figure 1"), counting only what is printed.

export function buildPages(blocks, isShown) {
  const pages = [{cover: true, reason: 'Cover page', items: []}]
  let current = pages[0]
  let sectionNumber = 0
  let tableNumber = 0
  let figureNumber = 0
  let insideHiddenSection = false
  let pendingBreak = false
  const hidden = []

  const hasContent = (page) => page.cover || page.items.length > 0
  const startPage = (reason) => {
    current = {cover: false, reason, items: []}
    pages.push(current)
  }

  for (const block of blocks) {
    const rule = isShown(block.showWhen)
    if (block.kind === 'section') {
      insideHiddenSection = !rule.shown
      if (insideHiddenSection) {
        hidden.push({block, reason: 'Section hidden by its rule'})
        continue
      }
      if (block.numbered !== false) sectionNumber += 1
      if ((block.newPage || pendingBreak) && hasContent(current)) {
        startPage(block.newPage ? `Section “${block.title}” starts a new page` : 'Page break')
      }
      pendingBreak = false
      current.items.push({block, number: block.numbered !== false ? sectionNumber : null, rule})
      continue
    }
    if (insideHiddenSection) {
      hidden.push({block, reason: 'Inside a hidden section'})
      continue
    }
    if (!rule.shown) {
      hidden.push({block, reason: 'Hidden by its rule'})
      continue
    }
    if (block.kind === 'pagebreak') {
      pendingBreak = true
      continue
    }
    if (pendingBreak && hasContent(current)) startPage('Page break')
    pendingBreak = false
    const item = {block, number: sectionNumber, rule}
    if (block.kind === 'table') item.caption = ++tableNumber
    if (block.kind === 'image') item.caption = ++figureNumber
    current.items.push(item)
  }
  return {pages, hidden}
}

// How a secret is printed. Technicians see the full value in the app (after an MFA check);
// the PDF shows at most a quarter of it, so a short password shows less, and a fixed run of dots hides its length.
export function maskSecret(value, settings = {pdf: 'partial', ends: 2}) {
  const text = String(value ?? '')
  if (!text) return ''
  if (settings.pdf === 'omit') return '[not printed]'
  const ends = Math.min(settings.ends ?? 2, Math.floor(text.length / 8))
  if (ends <= 0) return '••••••'
  return `${text.slice(0, ends)}••••••${text.slice(-ends)}`
}

const lookupPath = (data, path) => path.split('.').reduce((v, k) => (v == null ? undefined : v[k]), data)
const PLACEHOLDER = /(\{\{\s*[\w.]+\s*\}\})/g

// "{{answers.cvss}}" placeholders become parts; secrets are masked, unknown names are flagged.
// A text snippet ({{text.name}}) may itself use variables, but not other snippets.
export function interpolate(text, data, questions, depth = 0) {
  return String(text ?? '')
    .split(PLACEHOLDER)
    .filter((part) => part !== '')
    .flatMap((part) => {
      const match = part.match(/^\{\{\s*([\w.]+)\s*\}\}$/)
      if (!match) return [{text: part}]
      const name = match[1]
      if (name.startsWith('text.')) {
        const snippet = lookupPath(data, name)
        if (snippet === undefined || depth > 0) return [{name, text: `[unknown: ${name}]`, missing: true}]
        return interpolate(snippet, data, questions, depth + 1).map((p) => ({...p, snippet: name}))
      }
      const question = name.startsWith('answers.') ? questions.find((q) => q.key === name.slice(8)) : null
      const value = lookupPath(data, name)
      if (question?.type === 'secret') return [{name, text: maskSecret(value, question.secret) || '—', secret: true}]
      if (value === undefined) return [{name, text: `[unknown: ${name}]`, missing: true}]
      return [{name, text: formatValue(value, question?.type)}]
    })
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false})

export function formatValue(value, type) {
  if (value === undefined || value === null || value === '') return '—'
  if (type === 'secret') return maskSecret(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (type === 'datetime') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? String(value) : dateFormat.format(d)
  }
  if (typeof value === 'number') return value.toLocaleString('en-GB', {maximumFractionDigits: 2})
  if (Array.isArray(value)) return `${value.length} ${value.length === 1 ? 'row' : 'rows'}`
  return String(value)
}

// Accepts the usual written forms of IPv4 and IPv6 addresses (the server validates properly).
export function isIpAddress(value) {
  const v = String(value ?? '').trim()
  const v4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/
  if (v4.test(v)) return true
  if (!/^[0-9a-fA-F:]+$/.test(v) || !v.includes(':') || v.includes(':::')) return false
  if ((v.startsWith(':') && !v.startsWith('::')) || (v.endsWith(':') && !v.endsWith('::'))) return false
  const doubles = v.split('::').length - 1
  if (doubles > 1) return false
  const groups = v.split(':').filter((g) => g !== '')
  return groups.every((g) => g.length <= 4) && (doubles ? groups.length < 8 : groups.length === 8)
}
