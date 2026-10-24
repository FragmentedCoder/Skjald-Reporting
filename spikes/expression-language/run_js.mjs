// Run cases.json through @marcbachmann/cel-js (the browser-side CEL candidate) and write results/js.json.
// Same custom functions as the Python runner: xor, switch, re_match, re_replace, sum, lookup.
// re_match and re_replace use re2js (RE2 semantics, linear time), like google-re2 on the server.
// The built-in matches() uses JavaScript's RegExp and cannot be replaced; templates must not use it.

import {readFileSync, writeFileSync, mkdirSync} from 'node:fs'
import {performance} from 'node:perf_hooks'
import {Environment} from '@marcbachmann/cel-js'
import {RE2JS} from 're2js'

const here = new URL('.', import.meta.url)
const spec = JSON.parse(readFileSync(new URL('cases.json', here), 'utf8'))
const tables = spec.lookup_tables

// CEL distinguishes int and double; JSON does not. Whole numbers become BigInt (CEL int), as in Python.
const toCel = (v) => {
  if (typeof v === 'number' && Number.isInteger(v)) return BigInt(v)
  if (Array.isArray(v)) return v.map(toCel)
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, toCel(x)]))
  return v
}
const plain = (v) => {
  if (typeof v === 'bigint') return Number(v)
  if (v instanceof Date) return v.toISOString()
  if (v instanceof Map) return Object.fromEntries([...v].map(([k, x]) => [String(k), plain(x)]))
  if (Array.isArray(v)) return v.map(plain)
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plain(x)]))
  return v
}
const get = (m, k) => (m instanceof Map ? m.get(k) : m[k])
const has = (m, k) => (m instanceof Map ? m.has(k) : Object.hasOwn(m, k))

const env = new Environment({unlistedVariablesAreDyn: true, homogeneousAggregateLiterals: false})
  .registerFunction('xor(bool, bool): bool', (a, b) => a !== b)
  .registerFunction('switch(dyn, map<string, dyn>, dyn): dyn', (v, cases, d) => (has(cases, v) ? get(cases, v) : d))
  .registerFunction('re_match(string, string): bool', (t, p) => RE2JS.compile(p).matcher(t).find())
  .registerFunction('re_replace(string, string, string): string', (t, p, r) => RE2JS.compile(p).matcher(t).replaceAll(r))
  .registerFunction('string.replace(string, string): string', (s, from, to) => s.split(from).join(to))
  .registerFunction('sum(list<dyn>): dyn', (xs) => xs.reduce((a, b) => a + b, 0n))
  .registerFunction('lookup(string, string): string', (t, k) => tables[t][k])

const results = []
for (const c of spec.cases) {
  const start = performance.now()
  let value = null
  let error = null
  try {
    value = plain(env.evaluate(c.expr, toCel(c.vars)))
  } catch (err) {
    error = `${err.name}: ${err.message}`.slice(0, 300)
  }
  results.push({id: c.id, value, error, ms: Math.round((performance.now() - start) * 100) / 100})
}
mkdirSync(new URL('results/', here), {recursive: true})
writeFileSync(new URL('results/js.json', here), JSON.stringify(results, null, 2))
console.log(`js: ${results.length} cases run`)
