// Tests for the prototype's logic: pagination, variables and the CEL rules. Run with `npm test`.
import {test} from 'node:test'
import assert from 'node:assert/strict'
import {buildPages, interpolate, formatValue} from '../src/lib/pages.js'
import {evaluate, validate, toCelExpression} from '../src/lib/cel.js'
import {initialBlocks, initialQuestions, initialAnswers, context, computed} from '../src/lib/sample.js'

const dataFor = (answers) => {
  const data = {...context, answers}
  for (const c of computed) data[c.name] = evaluate(c.expr, data).value
  return data
}
const shownBy = (data) => (rule) => {
  if (!rule) return {shown: true}
  const r = evaluate(toCelExpression(rule, initialQuestions), data)
  return {shown: r.ok ? Boolean(r.value) : true, error: r.ok ? null : r.error}
}
const titles = (pages) => pages.map((p) => p.items.filter((i) => i.block.kind === 'section').map((i) => i.block.title))

test('major sections start on their own page', () => {
  const {pages} = buildPages(initialBlocks, shownBy(dataFor(initialAnswers)))
  assert.deepEqual(titles(pages), [['Summary'], ['Attacking addresses'], ['Actions taken'], ['Sign-off']])
  assert.equal(pages[0].cover, true)
  assert.match(pages[1].reason, /starts a new page/)
})

test('a hidden section takes its blocks with it, and no empty page is left', () => {
  const {pages, hidden} = buildPages(initialBlocks, shownBy(dataFor({...initialAnswers, attack_found: false})))
  assert.deepEqual(titles(pages), [['Summary'], ['Actions taken'], ['Sign-off']])
  assert.deepEqual(hidden.map((h) => h.block.id), ['b4', 'b5', 'b6'])
})

test('block rules hide single blocks', () => {
  const low = buildPages(initialBlocks, shownBy(dataFor({...initialAnswers, cvss: 5.0})))
  const ids = low.pages.flatMap((p) => p.items.map((i) => i.block.id))
  assert.ok(!ids.includes('b9') && !ids.includes('b10'))
})

test('a page break forces a page once, even right before a new-page section', () => {
  const blocks = [
    {id: 'a', kind: 'section', title: 'One', newPage: true},
    {id: 'b', kind: 'text', text: 'x'},
    {id: 'c', kind: 'pagebreak'},
    {id: 'd', kind: 'text', text: 'y'},
    {id: 'e', kind: 'pagebreak'},
    {id: 'f', kind: 'section', title: 'Two', newPage: true},
  ]
  const {pages} = buildPages(blocks, () => ({shown: true}))
  assert.deepEqual(pages.map((p) => p.items.map((i) => i.block.id)), [[], ['a', 'b'], ['d'], ['f']])
})

test('sections without "Start on a new page" continue the current page', () => {
  const blocks = [{id: 'a', kind: 'section', title: 'One', newPage: false}, {id: 'b', kind: 'section', title: 'Two', newPage: false}]
  const {pages} = buildPages(blocks, () => ({shown: true}))
  assert.equal(pages.length, 1)
  assert.deepEqual(pages[0].items.map((i) => i.number), [1, 2])
})

test('variables are filled in, secrets are masked, unknown names are flagged', () => {
  const data = dataFor(initialAnswers)
  const parts = interpolate('Severity {{severity_label}} ({{ answers.cvss }}), key {{answers.credentials}}, {{answers.nope}}', data, initialQuestions)
  const vars = parts.filter((p) => p.name)
  assert.deepEqual(vars.map((p) => p.text), ['High', '7.5', '••••••••', '[unknown: answers.nope]'])
  assert.ok(vars[2].secret && vars[3].missing)
})

test('values are formatted for the report', () => {
  assert.equal(formatValue(true), 'Yes')
  assert.equal(formatValue(1204), '1,204')
  assert.equal(formatValue('2026-10-21T03:14', 'datetime'), '21 October 2026 at 03:14')
  assert.equal(formatValue(''), '—')
})

test('visual rules become CEL', () => {
  assert.equal(toCelExpression({field: 'attack_found', op: 'is', value: true}, initialQuestions), 'answers.attack_found == true')
  assert.equal(toCelExpression({field: 'cvss', op: 'atLeast', value: 7}, initialQuestions), 'answers.cvss >= 7.0')
  assert.equal(toCelExpression({field: 'summary', op: 'matches', value: '^Between'}, initialQuestions), 're_match(answers.summary, "^Between")')
})

test('calculated values and the Skjald functions evaluate', () => {
  const data = dataFor(initialAnswers)
  assert.equal(data.severity_label, 'High')
  assert.equal(data.blocked_count, 2)
  assert.deepEqual(evaluate('sum(answers.attackers.map(a, a.attempts))', data), {ok: true, value: 1842})
  assert.deepEqual(evaluate('lookup("severity_da", severity_label.lowerAscii())', data), {ok: true, value: 'Høj'})
  assert.deepEqual(evaluate('xor(true, answers.cvss >= 9.0)', data), {ok: true, value: true})
  assert.deepEqual(evaluate('re_replace(answers.attackers[0].ip, "\\\\.[0-9]+$", ".x")', data), {ok: true, value: '198.51.100.x'})
})

test('the built-in matches() is rejected, and RE2 stays fast on hostile patterns', () => {
  assert.match(validate('answers.summary.matches("^(a+)+$")'), /not allowed/)
  assert.match(validate('matches(answers.summary, "x")'), /not allowed/)
  assert.equal(validate('re_match(answers.summary, "x")'), null)
  const started = performance.now()
  const r = evaluate('re_match(text, "^(a+)+$")', {text: `${'a'.repeat(5000)}!`})
  assert.deepEqual(r, {ok: true, value: false})
  assert.ok(performance.now() - started < 500)
})

test('very long expressions are refused', () => {
  assert.match(validate(`"${'a'.repeat(2500)}" == ""`), /limited to 2000/)
})

test('lookahead and other non-RE2 syntax is an error, not a silent pass', () => {
  assert.equal(evaluate('re_match("ab", "a(?=b)")', {}).ok, false)
})
