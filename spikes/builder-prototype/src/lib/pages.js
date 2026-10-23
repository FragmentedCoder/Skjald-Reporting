// Splits the layout into pages the way the PDF renderer does (docs/architecture.md, "Page breaks"):
// a section with "Start on a new page" begins a page, a page-break block forces one, and the cover is page 1.
// Very long sections still flow over more pages in the PDF; the preview flags pages that run over.

export function buildPages(blocks, isShown) {
  const pages = [{cover: true, reason: 'Cover page', items: []}]
  let current = pages[0]
  let sectionNumber = 0
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
      sectionNumber += 1
      if ((block.newPage || pendingBreak) && hasContent(current)) {
        startPage(block.newPage ? `Section “${block.title}” starts a new page` : 'Page break')
      }
      pendingBreak = false
      current.items.push({block, number: sectionNumber, rule})
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
    current.items.push({block, number: sectionNumber, rule})
  }
  return {pages, hidden}
}

const lookupPath = (data, path) => path.split('.').reduce((v, k) => (v == null ? undefined : v[k]), data)

// "{{answers.cvss}}" placeholders become parts; secrets are masked, unknown names are flagged.
export function interpolate(text, data, questions) {
  return String(text ?? '')
    .split(/(\{\{\s*[\w.]+\s*\}\})/g)
    .filter((part) => part !== '')
    .map((part) => {
      const match = part.match(/^\{\{\s*([\w.]+)\s*\}\}$/)
      if (!match) return {text: part}
      const name = match[1]
      const question = name.startsWith('answers.') ? questions.find((q) => q.key === name.slice(8)) : null
      if (question?.type === 'secret') return {name, text: '••••••••', secret: true}
      const value = lookupPath(data, name)
      if (value === undefined) return {name, text: `[unknown: ${name}]`, missing: true}
      return {name, text: formatValue(value, question?.type)}
    })
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false})

export function formatValue(value, type) {
  if (value === undefined || value === null || value === '') return '—'
  if (type === 'secret') return '••••••••'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (type === 'datetime') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? String(value) : dateFormat.format(d)
  }
  if (typeof value === 'number') return value.toLocaleString('en-GB', {maximumFractionDigits: 2})
  if (Array.isArray(value)) return `${value.length} rows`
  return String(value)
}
