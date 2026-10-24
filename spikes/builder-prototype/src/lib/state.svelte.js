import {initialQuestions, initialBlocks, initialAnswers, initialLibrary, context, computed, coverFacts, lookupTablesFrom, USERS} from './sample.js'
import {evaluate, toCelExpression, setLookupSource} from './cel.js'

// The template being edited. Lists handed to svelte-dnd-action are replaced on every change, never mutated in place.
export const doc = $state({
  questions: initialQuestions,
  blocks: initialBlocks,
  answers: structuredClone(initialAnswers),
  computed: structuredClone(computed),
  coverFacts: structuredClone(coverFacts),
  selectedBlock: 'b6',
  selectedQuestion: 'q7',
})

// The shared library (variables, text snippets, data tables), used by every template and report.
export const library = $state(structuredClone(initialLibrary))
setLookupSource(() => lookupTablesFrom(library))

// Who is looking, which screen is open, and what has happened in this visit.
export const session = $state({role: 'designer', view: 'layout', notice: '', activity: [], introClosed: false})
export const currentUser = () => USERS[session.role]
export const canBuild = () => session.role !== 'technician'

export function log(change) {
  session.activity = [{at: new Date().toISOString(), by: currentUser().name, change}, ...session.activity].slice(0, 20)
}

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

// Renaming a question's variable updates every block, rule, cover fact and calculated value that uses it.
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
  doc.blocks = doc.blocks.map((b) => ({...b, question: b.question === old ? next : b.question, showWhen: fixRule(b.showWhen),
    text: fixText(b.text), title: fixText(b.title)}))
  doc.coverFacts = doc.coverFacts.map((f) => ({...f, text: fixText(f.text)}))
  const {[old]: value, ...rest} = doc.answers
  doc.answers = {...rest, [next]: value}
  return null
}

// Every question has a value, so rules never fail on a missing answer.
const EMPTY = {repeating: () => [], yesno: () => null, number: () => null, datetime: () => null}
export function withDefaults(answers, questions) {
  const filled = {...answers}
  for (const q of questions) {
    if (q.type === 'group' || filled[q.key] !== undefined) continue
    filled[q.key] = EMPTY[q.type]?.() ?? ''
  }
  return filled
}

// Everything a template can read: context, answers, the library and calculated values (evaluated with CEL).
export function templateData(answers) {
  const data = {
    ...context,
    answers: withDefaults(answers, doc.questions),
    vars: Object.fromEntries(library.vars.map((v) => [v.key, v.value])),
    text: Object.fromEntries(library.text.map((t) => [t.key, t.value])),
  }
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

// Which PDF blocks use a question, so the builder can show where an answer ends up.
export function usage(key) {
  const name = new RegExp(`answers\\.${key}(?!\\w)`)
  const uses = (b) => b.question === key || b.showWhen?.field === key || name.test(`${b.text ?? ''} ${b.title ?? ''} ${b.intro ?? ''} ${b.caption ?? ''}`)
  const onCover = doc.coverFacts.some((f) => name.test(f.text))
  return [...(onCover ? [{id: 'cover', kind: 'cover'}] : []), ...doc.blocks.filter(uses)]
}

// Library edits are logged with who and when; locked entries can only be changed by an administrator.
export function editLibrary(kind, key, patch, change) {
  library[kind] = library[kind].map((entry) => entry.key !== key ? entry : {
    ...entry, ...patch, history: [...entry.history, {at: new Date().toISOString().slice(0, 16), by: currentUser().name, change}],
  })
  log(`Library entry ${kind === 'tables' ? `table ${key}` : `${kind}.${key}`}: ${change}`)
}
