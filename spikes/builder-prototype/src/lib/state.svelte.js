import {initialQuestions, initialBlocks, initialAnswers, context, computed, coverFacts} from './sample.js'
import {evaluate, toCelExpression} from './cel.js'

// Lists handed to svelte-dnd-action are replaced on every change, never mutated in place.
export const doc = $state({
  tab: 'layout',
  questions: initialQuestions,
  blocks: initialBlocks,
  answers: structuredClone(initialAnswers),
  computed: structuredClone(computed),
  coverFacts: structuredClone(coverFacts),
  selectedBlock: 'b4',
  selectedQuestion: 'q5',
  notice: '',
})

export function updateBlock(id, patch) {
  doc.blocks = doc.blocks.map((b) => (b.id === id ? {...b, ...patch} : b))
}

export function updateQuestion(id, patch) {
  doc.questions = doc.questions.map((q) => (q.id === id ? {...q, ...patch} : q))
}

export function removeBlock(id) {
  const index = doc.blocks.findIndex((b) => b.id === id)
  doc.blocks = doc.blocks.filter((b) => b.id !== id)
  doc.selectedBlock = doc.blocks[Math.max(0, index - 1)]?.id ?? null
}

export function removeQuestion(id) {
  const index = doc.questions.findIndex((q) => q.id === id)
  doc.questions = doc.questions.filter((q) => q.id !== id)
  doc.selectedQuestion = doc.questions[Math.max(0, index - 1)]?.id ?? null
}

export const KEY_PATTERN = /^[a-z][a-z0-9_]{0,39}$/

// Renaming a question's variable updates every block, rule and text that uses it.
export function renameKey(id, next) {
  const q = doc.questions.find((x) => x.id === id)
  if (!q || q.key === next) return null
  if (!KEY_PATTERN.test(next)) return 'Use lower-case letters, digits and underscores, starting with a letter.'
  if (doc.questions.some((x) => x.key === next)) return 'Another question already uses this name.'
  const old = q.key
  const fixRule = (r) => (r && r.field === old ? {...r, field: next} : r)
  const fixText = (t) => (typeof t === 'string' ? t.replace(new RegExp(`\\{\\{\\s*answers\\.${old}\\s*\\}\\}`, 'g'), `{{answers.${next}}}`) : t)
  // Calculated values are CEL text; rename the identifier answers.<old> wherever it appears as a whole name.
  const ident = new RegExp(`(?<![\\w.])answers\\.${old}(?!\\w)`, 'g')
  doc.computed = doc.computed.map((c) => ({...c, expr: c.expr.replace(ident, `answers.${next}`)}))
  doc.questions = doc.questions.map((x) => ({...x, key: x.id === id ? next : x.key, showWhen: fixRule(x.showWhen)}))
  doc.blocks = doc.blocks.map((b) => ({...b, question: b.question === old ? next : b.question, showWhen: fixRule(b.showWhen), text: fixText(b.text)}))
  doc.coverFacts = doc.coverFacts.map((f) => ({...f, text: fixText(f.text)}))
  const {[old]: value, ...rest} = doc.answers
  doc.answers = {...rest, [next]: value}
  return null
}

// Everything a template can read: context, answers and calculated values (evaluated with CEL).
export function templateData(answers) {
  const data = {...context, answers}
  for (const c of doc.computed) {
    const result = evaluate(c.expr, data)
    data[c.name] = result.ok ? result.value : `[${c.name}: ${result.error}]`
  }
  return data
}

export function ruleResult(rule, data) {
  if (!rule) return {expr: '', ok: true, value: true}
  const expr = toCelExpression(rule, doc.questions)
  if (!expr) return {expr, ok: false, value: true, error: 'The question this rule uses was removed'}
  return {expr, ...evaluate(expr, data)}
}
