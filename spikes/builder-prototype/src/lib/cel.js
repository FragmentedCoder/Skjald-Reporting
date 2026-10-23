// CEL in the browser: cel-js plus Skjald's function library, regexes on RE2 (re2js),
// as decided in spikes/expression-language.
import {Environment} from '@marcbachmann/cel-js'
import {RE2JS} from 're2js'
import {lookupTables} from './sample.js'

const has = (m, k) => (m instanceof Map ? m.has(k) : Object.hasOwn(m, k))
const get = (m, k) => (m instanceof Map ? m.get(k) : m[k])

const env = new Environment({unlistedVariablesAreDyn: true, homogeneousAggregateLiterals: false})
  .registerFunction('xor(bool, bool): bool', (a, b) => a !== b)
  .registerFunction('switch(dyn, map<string, dyn>, dyn): dyn', (v, cases, d) => (has(cases, v) ? get(cases, v) : d))
  .registerFunction('re_match(string, string): bool', (t, p) => RE2JS.compile(p).matcher(t).find())
  .registerFunction('re_replace(string, string, string): string', (t, p, r) => RE2JS.compile(p).matcher(t).replaceAll(r))
  .registerFunction('string.replace(string, string): string', (s, a, b) => s.split(a).join(b))
  .registerFunction('sum(list<dyn>): dyn', (xs) => xs.reduce((a, b) => a + b, 0n))
  .registerFunction('lookup(string, string): string', (t, k) => lookupTables[t]?.[k] ?? '')

// CEL tells whole numbers (int) from decimals (double); JSON-like data does not.
const toCel = (v) => {
  if (typeof v === 'number' && Number.isInteger(v)) return BigInt(v)
  if (Array.isArray(v)) return v.map(toCel)
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, toCel(x)]))
  return v
}
const fromCel = (v) => {
  if (typeof v === 'bigint') return Number(v)
  if (Array.isArray(v)) return v.map(fromCel)
  if (v instanceof Map) return Object.fromEntries([...v].map(([k, x]) => [String(k), fromCel(x)]))
  if (v && typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, fromCel(x)]))
  return v
}

// The template validator: the built-in matches() runs on JavaScript's backtracking RegExp, so it is rejected.
const MAX_LENGTH = 2000
const BANNED = {matches: 'matches() is not allowed in templates; use re_match()'}

function findBanned(node) {
  if (Array.isArray(node)) return node.map(findBanned).find(Boolean)
  if (!node || typeof node !== 'object') return null
  if ((node.op === 'call' || node.op === 'rcall') && BANNED[node.args?.[0]]) return BANNED[node.args[0]]
  return findBanned(node.args)
}

export function validate(expr) {
  if (expr.length > MAX_LENGTH) return `Expressions are limited to ${MAX_LENGTH} characters`
  try {
    return findBanned(env.parse(expr).ast) ?? null
  } catch (err) {
    return err.message.split('\n')[0]
  }
}

export function evaluate(expr, data) {
  const invalid = validate(expr)
  if (invalid) return {ok: false, error: invalid}
  try {
    return {ok: true, value: fromCel(env.evaluate(expr, toCel(data)))}
  } catch (err) {
    return {ok: false, error: err.message.split('\n')[0]}
  }
}

export const OPERATORS = {
  is: {label: 'is', types: ['yesno', 'text', 'dropdown', 'number', 'ip']},
  isNot: {label: 'is not', types: ['yesno', 'text', 'dropdown', 'number', 'ip']},
  atLeast: {label: 'is at least', types: ['number']},
  atMost: {label: 'is at most', types: ['number']},
  matches: {label: 'matches pattern', types: ['text', 'ip', 'longtext']},
}

const literal = (value, type) => {
  if (type === 'yesno') return value ? 'true' : 'false'
  if (type === 'number') return Number.isFinite(Number(value)) ? String(Number(value)).replace(/^(-?\d+)$/, '$1.0') : '0.0'
  return JSON.stringify(String(value ?? ''))
}

// The visual rule ({field, op, value}) becomes a CEL expression; this is what gets stored.
export function toCelExpression(rule, questions) {
  if (!rule) return ''
  const q = questions.find((x) => x.key === rule.field)
  if (!q) return ''
  const ref = `answers.${q.key}`
  const v = literal(rule.value, q.type)
  switch (rule.op) {
    case 'is': return `${ref} == ${v}`
    case 'isNot': return `${ref} != ${v}`
    case 'atLeast': return `${ref} >= ${v}`
    case 'atMost': return `${ref} <= ${v}`
    case 'matches': return `re_match(${ref}, ${JSON.stringify(String(rule.value ?? ''))})`
    default: return ''
  }
}

export function describeRule(rule, questions) {
  if (!rule) return ''
  const q = questions.find((x) => x.key === rule.field)
  if (!q) return 'Rule refers to a removed question'
  const value = q.type === 'yesno' ? (rule.value ? 'Yes' : 'No') : String(rule.value)
  return `“${q.label}” ${OPERATORS[rule.op]?.label ?? rule.op} ${value}`
}
