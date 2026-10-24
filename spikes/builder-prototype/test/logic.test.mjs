// Tests for the prototype's logic: pagination, variables, secrets, colours and the CEL rules. Run with `npm test`.
import {test} from 'node:test'
import assert from 'node:assert/strict'
import {buildPages, interpolate, formatValue, maskSecret, isIpAddress} from '../src/lib/pages.js'
import {evaluate, validate, toCelExpression} from '../src/lib/cel.js'
import {calloutColours, contrast, TONES} from '../src/lib/colour.js'
import {initialBlocks, initialQuestions, initialAnswers, initialLibrary, context, computed} from '../src/lib/sample.js'

const dataFor = (answers) => {
  const data = {
    ...context, answers,
    vars: Object.fromEntries(initialLibrary.vars.map((v) => [v.key, v.value])),
    text: Object.fromEntries(initialLibrary.text.map((t) => [t.key, t.value])),
  }
  for (const c of computed) data[c.name] = evaluate(c.expr, data).value
  return data
}
const shownBy = (data) => (rule) => {
  if (!rule) return {shown: true}
  const r = evaluate(toCelExpression(rule, initialQuestions), data)
  return {shown: r.ok ? Boolean(r.value) : true, error: r.ok ? null : r.error}
}
const titles = (pages) => pages.map((p) => p.items.filter((i) => i.block.kind === 'section').map((i) => i.block.title))

test('major sections start on their own page; a section set to continue stays on the page', () => {
  const {pages} = buildPages(initialBlocks, shownBy(dataFor(initialAnswers)))
  assert.deepEqual(titles(pages), [['Summary'], ['Attacking addresses'], ['Actions taken', 'Sources'], ['Sign-off']])
  assert.equal(pages[0].cover, true)
  assert.match(pages[1].reason, /starts a new page/)
})

test('a hidden section takes its blocks with it, and no empty page is left', () => {
  const {pages, hidden} = buildPages(initialBlocks, shownBy(dataFor({...initialAnswers, attack_found: false})))
  assert.deepEqual(titles(pages), [['Summary'], ['Actions taken', 'Sources'], ['Sign-off']])
  assert.deepEqual(hidden.map((h) => h.block.id), ['b4', 'b5', 'b6', 'b13'])
})

test('block rules hide single blocks', () => {
  const none = buildPages(initialBlocks, shownBy(dataFor({...initialAnswers, credentials: '', evidence: ''})))
  const ids = none.pages.flatMap((p) => p.items.map((i) => i.block.id))
  assert.ok(!ids.includes('b9') && !ids.includes('b10') && !ids.includes('b13'))
})

test('tables and figures are numbered in reading order, counting only printed ones', () => {
  const all = buildPages(initialBlocks, shownBy(dataFor(initialAnswers))).pages.flatMap((p) => p.items)
  assert.deepEqual(all.filter((i) => i.caption).map((i) => [i.block.id, i.caption]), [['b6', 1], ['b13', 1], ['b14', 2]])
  const noAttack = buildPages(initialBlocks, shownBy(dataFor({...initialAnswers, attack_found: false}))).pages.flatMap((p) => p.items)
  assert.deepEqual(noAttack.filter((i) => i.caption).map((i) => [i.block.id, i.caption]), [['b14', 1]])
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

test('unnumbered sections do not take a number', () => {
  const blocks = [{id: 'a', kind: 'section', title: 'One'}, {id: 'b', kind: 'section', title: 'Appendix', numbered: false}, {id: 'c', kind: 'section', title: 'Two'}]
  const {pages} = buildPages(blocks, () => ({shown: true}))
  assert.deepEqual(pages[0].items.map((i) => i.number), [1, null, 2])
})

test('secrets: at most a quarter is printed, the length is hidden, or nothing at all', () => {
  assert.equal(maskSecret('Hunter2-portal-admin'), 'Hu••••••in')
  assert.equal(maskSecret('Hunter2-portal-admin', {pdf: 'partial', ends: 3}), 'Hu••••••in')
  assert.equal(maskSecret('abcdefghijklmnopqrstuvwx', {pdf: 'partial', ends: 3}), 'abc••••••vwx')
  assert.equal(maskSecret('Summer26', {pdf: 'partial', ends: 2}), 'S••••••6')
  assert.equal(maskSecret('short', {pdf: 'partial', ends: 2}), '••••••')
  assert.equal(maskSecret('Hunter2-portal-admin', {pdf: 'omit'}), '[not printed]')
  assert.equal(maskSecret(''), '')
})

test('variables, library values and snippets are filled in; secrets are masked; unknown names are flagged', () => {
  const data = dataFor(initialAnswers)
  const parts = interpolate('{{severity_label}} ({{ answers.cvss }}), {{vars.support_phone}}, {{answers.credentials}}, {{answers.nope}}', data, initialQuestions)
  const vars = parts.filter((p) => p.name)
  assert.deepEqual(vars.map((p) => p.text), ['High', '7.5', '+45 12 34 56 78', 'Hu••••••in', '[unknown: answers.nope]'])
  const snippet = interpolate('{{text.password_handover}}', data, initialQuestions).map((p) => p.text).join('')
  assert.equal(snippet, 'The full password was given to Jens Hansen by phone, and must be changed at the first sign-in.')
})

test('a snippet cannot pull in another snippet', () => {
  const data = {...dataFor(initialAnswers), text: {a: 'A then {{text.b}}', b: 'B'}}
  const parts = interpolate('{{text.a}}', data, initialQuestions)
  assert.ok(parts.some((p) => p.missing && p.name === 'text.b'))
})

test('values are formatted for the report', () => {
  assert.equal(formatValue(true), 'Yes')
  assert.equal(formatValue(1204), '1,204')
  assert.equal(formatValue('2026-10-21T03:14', 'datetime'), '21 October 2026 at 03:14')
  assert.equal(formatValue(''), '—')
})

test('IP addresses are checked in the form', () => {
  for (const ok of ['198.51.100.23', '2001:db8::5', '::1', '2001:0db8:0000:0000:0000:ff00:0042:8329']) assert.ok(isIpAddress(ok), ok)
  for (const bad of ['198.51.100', '256.1.1.1', '2001:db8:::5', 'portal', '']) assert.ok(!isIpAddress(bad), bad)
})

test('callout tones and custom colours keep text readable', () => {
  for (const tone of Object.values(TONES)) assert.ok(contrast(tone.bg, tone.fg) >= 4.5, tone.label)
  assert.deepEqual(calloutColours({tone: 'custom', color: '#0F1B2D'}).fg, '#FFFFFF')
  assert.deepEqual(calloutColours({tone: 'custom', color: '#FBEFD9'}).fg, '#0F1B2D')
  const mid = calloutColours({tone: 'custom', color: '#7F7F7F'})
  assert.equal(mid.ok, false)
})

test('visual rules become CEL', () => {
  assert.equal(toCelExpression({field: 'attack_found', op: 'is', value: true}, initialQuestions), 'answers.attack_found == true')
  assert.equal(toCelExpression({field: 'cvss', op: 'atLeast', value: 7}, initialQuestions), 'answers.cvss >= 7.0')
  assert.equal(toCelExpression({field: 'summary', op: 'matches', value: '^Between'}, initialQuestions), 're_match(answers.summary, "^Between")')
  assert.equal(toCelExpression({field: 'credentials', op: 'isFilled', value: ''}, initialQuestions), 'answers.credentials != ""')
})

test('calculated values and the Skjald functions evaluate, lookups read the library', () => {
  const data = dataFor(initialAnswers)
  assert.equal(data.severity_label, 'High')
  assert.equal(data.blocked_count, 2)
  assert.deepEqual(evaluate('sum(answers.attackers.map(a, a.attempts))', data), {ok: true, value: 1842})
  assert.deepEqual(evaluate('lookup("severity_da", severity_label.lowerAscii())', data), {ok: true, value: 'Høj'})
  assert.deepEqual(evaluate('lookup("media_destruction", "ssd")', data), {ok: true, value: 'Shredded to 2 mm (NIST SP 800-88, Destroy)'})
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
