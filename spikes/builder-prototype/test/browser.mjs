// Browser checks for the built prototype: roles, drag and drop, element settings, page breaks, rules, secrets,
// the library, the report check, both themes and phone width. No errors and no network requests.
// Run with `npm run check:browser` after `npm run build`. Screenshots go to dist/shots.
import {chromium} from 'playwright'
import {mkdirSync} from 'node:fs'
import path from 'node:path'

const file = 'file://' + path.resolve('dist/index.html')
const out = 'dist/shots'
mkdirSync(out, {recursive: true})
const results = []
const ok = (name, cond, detail = '') => results.push({name, pass: !!cond, detail})

async function drag(page, from, to, {dx = 0, dy = 6} = {}) {
  const s = await from.boundingBox()
  const t = await to.boundingBox()
  const sx = s.x + 24, sy = s.y + s.height / 2
  const tx = t.x + 60 + dx, ty = t.y + dy
  await page.mouse.move(sx, sy)
  await page.mouse.down()
  for (let i = 1; i <= 25; i++) await page.mouse.move(sx + ((tx - sx) * i) / 25, sy + ((ty - sy) * i) / 25)
  await page.waitForTimeout(300)
  await page.mouse.up()
  await page.waitForTimeout(400)
}
const kinds = (page) => page.locator('.blocks .block').evaluateAll((els) => els.map((e) => [...e.classList].find((c) => c.startsWith('kind-'))))
const pdfText = (page) => page.locator('.pages').innerText()
const sectionsPerPage = (page) => page.locator('.sheet').evaluateAll((els) => els.map((e) => [...e.querySelectorAll('h2.section')].map((h) => h.textContent.replace(/^\d+/, ''))))

const browser = await chromium.launch()
const page = await browser.newPage({viewport: {width: 1440, height: 1400}})
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`) })
const requests = []
page.on('request', (r) => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:') && !r.url().startsWith('blob:')) requests.push(r.url()) })

// ---- Template builder, as a report designer
await page.goto(file + '#layout')
await page.waitForSelector('.blocks .block')
await page.evaluate(() => document.fonts.ready)
ok('fonts load from the bundle', await page.evaluate(() => ['Marcellus', 'IBM Plex Sans', 'Mr Dafoe'].every((f) => document.fonts.check(`16px "${f}"`))))
ok('builder explains who sees what', (await page.locator('.legend').innerText()).includes('Technicians never see this screen'))
await page.screenshot({path: `${out}/layout-light.png`, fullPage: true})

const before = await page.locator('.blocks .block').count()
await drag(page, page.locator('.palette .entry', {hasText: 'Page break'}), page.locator('.blocks .block', {hasText: 'Actions taken'}).first(), {dy: -4})
const k1 = await kinds(page)
ok('drag a block from the palette onto the page', (await page.locator('.blocks .block').count()) === before + 1 && (await page.locator('.props h2').first().textContent()).trim() === 'Page break')
ok('it lands where it was dropped', k1[k1.indexOf('kind-pagebreak') + 1] === 'kind-section', k1.join(','))
ok('the palette keeps its entries', (await page.locator('.palette .entry').count()) === 10)

await drag(page, page.locator('.blocks .block.kind-table'), page.locator('.blocks .block', {hasText: 'Traffic from these addresses'}), {dx: -20})
const order = await kinds(page)
ok('blocks reorder by dragging', order.indexOf('kind-table') < order.indexOf('kind-text'), order.join(','))
await drag(page, page.locator('.blocks .block', {hasText: 'Traffic from these addresses'}), page.locator('.blocks .block.kind-table'), {dx: -20})
ok('and back', (await kinds(page)).indexOf('kind-table') > (await kinds(page)).indexOf('kind-text'))

await page.locator('.blocks .block', {hasText: 'Summary'}).first().locator('.pick').click()
await page.locator('.palette .entry', {hasText: 'Callout'}).click()
ok('click adds after the selected block', (await kinds(page))[1] === 'kind-callout')
await page.locator('.tone', {hasText: 'Custom'}).click()
await page.locator('.colour-row .input').fill('#0F1B2D')
ok('a dark custom colour gets light text and passes', (await page.locator('.props .pill.ok', {hasText: 'Readable'}).count()) === 1)
await page.locator('.colour-row .input').fill('#7F7F7F')
ok('an unreadable custom colour is flagged', (await page.locator('.props .pill', {hasText: 'Hard to read'}).count()) === 1)
await page.locator('.props .btn', {hasText: 'Remove'}).first().click()

await page.locator('.blocks .block.kind-signatures .pick').click()
await page.locator('.props .btn', {hasText: 'Add a signature box'}).click()
ok('a signature box can be added', (await page.locator('.blocks .block.kind-signatures .sig').count()) === 4)
await page.locator('.props .signer').last().getByRole('button').click()
ok('and removed', (await page.locator('.blocks .block.kind-signatures .sig').count()) === 3)

await page.locator('.blocks .block.kind-table .pick').click()
await page.locator('.props .list-row', {hasText: 'Status'}).getByRole('checkbox').uncheck()
ok('a table column can be left out', (await page.locator('.blocks .block.kind-table .mini-table span').count()) === 2)

await page.locator('.blocks .block', {hasText: 'Attacking addresses'}).first().locator('.pick').click()
ok('section rules are stored as CEL', (await page.locator('.props .cel code').textContent()).trim() === 'answers.attack_found == true')

// ---- Questions tab
await page.getByRole('tab', {name: /Questions/}).click()
const qBefore = await page.locator('.cards .card').count()
await drag(page, page.locator('.palette .entry', {hasText: 'Dropdown'}), page.locator('.cards .card', {hasText: 'Actions taken'}), {dy: 10})
ok('drag a field type into the form', (await page.locator('.cards .card').count()) === qBefore + 1 && (await page.locator('.props h2').first().textContent()).trim() === 'Dropdown')
await page.locator('.props .btn', {hasText: 'Remove'}).click()
ok('each question says where it is printed', (await page.locator('.card', {hasText: 'Detected at'}).innerText()).includes('the cover page'))
await page.locator('.card', {hasText: 'New portal admin password'}).locator('.pick').click()
await page.locator('#q-secret-pdf').selectOption('omit')
ok('a secret can be left out of the PDF', (await page.locator('.card', {hasText: 'New portal admin password'}).innerText()).includes('[not printed]'))
await page.locator('#q-secret-pdf').selectOption('partial')
// ---- Data tab
await page.getByRole('tab', {name: /Data/}).click()
ok('the data tab explains with a worked example', (await page.locator('.example.big').innerText()).includes('Prepared for Fjordvik Logistik A/S by Freja Holm'))
ok('every function shows a live result', (await page.locator('.fn .res').count()) === 14 && !(await page.locator('.fn .res').allInnerTexts()).some((t) => /error|no such/i.test(t)))
await page.locator('.fn tr', {hasText: 'sum(list)'}).getByRole('button', {name: 'Try'}).click()
ok('Try puts the example in the playground', (await page.locator('#d-try .outcome').innerText()).includes('1842'))
await page.locator('#try').fill('answers.summary.matches("^(a+)+$")')
ok('the built-in matches() is refused', (await page.locator('#d-try .outcome').innerText()).includes('Not allowed'))
await page.screenshot({path: `${out}/data-light.png`, fullPage: true})

await page.getByRole('tab', {name: /Questions/}).click()
await page.locator('.card', {hasText: 'Highest CVSS score'}).locator('.pick').click()
await page.locator('#q-key').fill('Bad Name')
await page.locator('#q-key').press('Enter')
ok('an invalid variable name is refused', (await page.locator('.props .error').count()) === 1)
await page.locator('#q-key').fill('cvss_score')
await page.locator('#q-key').press('Enter')
await page.screenshot({path: `${out}/questions-light.png`, fullPage: true})

// ---- Try it as a technician
await page.getByRole('tab', {name: /Try it/}).click()
await page.waitForSelector('.sheet')
await page.evaluate(() => document.fonts.ready)
ok('the preview says it is the technician\'s screen', (await page.locator('.explain').innerText()).includes('This is what a technician sees'))
ok('4 pages with the sample answers', (await page.locator('.sheet').count()) === 4)
ok('each major section starts its own page', JSON.stringify(await sectionsPerPage(page)) === JSON.stringify([['Summary'], ['Attacking addresses'], ['Actions taken', 'Sources'], ['Sign-off']]), JSON.stringify(await sectionsPerPage(page)))
let text = await pdfText(page)
ok('a renamed variable still fills the text and the cover', text.includes('Highest CVSS score 7.5') && text.includes('High · CVSS 7.5'))
ok('the secret is printed only partly', text.includes('Hu••••••in') && !text.includes('Hunter2-portal-admin'))
ok('tables and figures are numbered', text.includes('Table 1.') && text.includes('Figure 1.') && text.includes('Figure 2.'))
ok('the left-out column is not printed', !(await page.locator('.sheet th', {hasText: 'Status'}).count()))
ok('library values and snippets are printed', text.includes('+45 12 34 56 78') && text.includes('given to Jens Hansen by phone'))
ok('sources from the template and the technician are listed', text.includes('[1]') && text.includes('[2]') && text.includes('VA-2026-117'))
ok('the footer counts pages', (await page.locator('.sheet .run-foot').last().textContent()).includes('Page 4 of 4'))
await page.screenshot({path: `${out}/try-light.png`, fullPage: true})

await page.locator('.steps button', {hasText: 'The attack'}).click()
await page.locator('fieldset.repeat input[aria-label="Address, row 1"]').fill('198.51.100')
ok('an invalid IP address is flagged in the form', (await page.locator('.step .error', {hasText: 'not a valid'}).count()) === 1)
await page.locator('fieldset.repeat input[aria-label="Address, row 1"]').fill('198.51.100.23')
await page.locator('.step fieldset.yesno').getByLabel('No').check()
await page.waitForTimeout(100)
ok('answering No removes the section and its page', (await page.locator('.sheet').count()) === 3)
ok('and hides the follow-up question', (await page.locator('fieldset.repeat').count()) === 0)
await page.locator('.step fieldset.yesno').getByLabel('Yes').check()
await page.locator('.step .file-input').setInputFiles({name: 'graph.png', mimeType: 'image/png',
  buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64')})
await page.waitForTimeout(200)
ok('an uploaded photo goes into the PDF', (await page.locator('.sheet figure img[src^="data:image/png"]').count()) === 1)

await page.locator('.steps button', {hasText: 'Actions and handover'}).click()
await page.locator('.secret .btn', {hasText: 'Reveal'}).click()
await page.locator('.mfa .input').fill('123')
await page.locator('.mfa .btn', {hasText: 'Confirm'}).click()
ok('revealing a secret needs a 6-digit code', (await page.locator('.mfa .error').count()) === 1)
await page.locator('.mfa .input').fill('123456')
await page.locator('.mfa .btn', {hasText: 'Confirm'}).click()
ok('then shows it for 30 seconds', (await page.locator('#ans-credentials').getAttribute('type')) === 'text' && (await page.locator('.secret .note').innerText()).includes('logged'))
await page.locator('.secret .btn', {hasText: 'Hide now'}).click()
ok('and hides it again', (await page.locator('#ans-credentials').getAttribute('type')) === 'password')
await page.locator('#ans-credentials').fill('')
await page.waitForTimeout(100)
ok('an empty secret leaves out the blocks that need it', !(await pdfText(page)).includes('New credentials'))
await page.locator('#ans-credentials').fill('Hunter2-portal-admin')
await page.locator('#ans-actions').fill('Long text. '.repeat(900))
await page.waitForTimeout(300)
const overInfo = await page.locator('.sheet').evaluateAll((els) => els.map((e) => `${e.offsetWidth}x${e.offsetHeight}${e.classList.contains('over') ? ' over' : ''}`))
ok('a page longer than A4 is flagged', (await page.locator('.sheet.over', {hasText: 'Actions taken'}).count()) === 1, overInfo.join(', '))
await page.locator('#ans-actions').fill('')
await page.locator('.steps button', {hasText: 'Review and send'}).click()
ok('review lists what is missing', (await page.locator('.checklist').innerText()).includes('Actions taken'))
ok('the reveal was logged', (await page.locator('.activity').innerText()).includes('Revealed'))
await page.locator('.steps button', {hasText: 'Actions and handover'}).click()
await page.locator('#ans-actions').fill('Firewall rules were added for both addresses.')

// ---- Library and roles
await page.locator('#role').selectOption('technician')
ok('technicians do not see Templates', !(await page.locator('.nav button', {hasText: 'Templates'}).count()) && (await page.locator('.report .head h1').innerText()) === 'INC-2026-0142')
await page.locator('.nav button', {hasText: 'Library'}).click()
await page.locator('#v-support_phone').fill('+45 87 65 43 21')
await page.locator('#v-support_phone').press('Tab')
const phone = page.locator('.entry', {hasText: 'vars.support_phone'})
ok('a technician can change a library entry, and it is logged', (await phone.getByRole('button', {name: /History/}).innerText()).includes('(2)'))
ok('but not a locked one', await page.locator('#v-retention_years').isDisabled())
await page.locator('#new-key').fill('Service Window')
await page.locator('.add-form .btn', {hasText: 'Add'}).click()
ok('a bad library name is refused', (await page.locator('.add-form .error').count()) === 1)
await page.locator('#new-key').fill('service_window')
await page.locator('#new-value').fill('Weekdays 08:00–16:00')
await page.locator('.add-form .btn', {hasText: 'Add'}).click()
ok('a new library entry can be added', (await page.locator('.entry', {hasText: 'vars.service_window'}).count()) === 1)
await page.locator('.nav button', {hasText: 'Reports'}).click()
ok('reports use the new library value', (await pdfText(page)).includes('+45 87 65 43 21'))
await page.locator('#role').selectOption('admin')
await page.locator('.nav button', {hasText: 'Library'}).click()
ok('an administrator can change locked entries and lock others', !(await page.locator('#v-retention_years').isDisabled()) && (await page.locator('.entry-foot .btn', {hasText: 'Lock'}).count()) >= 2)
await page.screenshot({path: `${out}/library-light.png`, fullPage: true})

// ---- Check a signed report
await page.locator('.nav button', {hasText: 'Check a report'}).click()
await page.getByRole('button', {name: 'The signed sample report'}).click()
let res = await page.locator('.result').innerText()
ok('the signed sample checks out, and Skjald knows the file', res.includes('Signed and unchanged') && res.includes('INC-2026-0142') && (await page.locator('.result .pill', {hasText: 'Intact'}).count()) === 3)
await page.getByRole('button', {name: 'A copy with one byte changed'}).click()
res = await page.locator('.result').innerText()
ok('an edited copy is caught', res.includes('Changed after it was signed') && (await page.locator('.result .pill', {hasText: 'Broken'}).count()) === 3 && res.includes('No report in Skjald'))
await page.locator('#check-file').setInputFiles({name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello')})
await page.waitForTimeout(200)
ok('a file that is not a PDF is reported as such', (await page.locator('.result').innerText()).includes('not a readable PDF'))
await page.locator('#check-file').setInputFiles({name: 'other.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\n1 0 obj << /Type /Sig /ByteRange [0 10 20 30] >> endobj\n%%EOF')})
await page.waitForTimeout(200)
res = await page.locator('.result').innerText()
ok('an uploaded PDF is hashed and its signatures counted, clearly unverified', res.includes('Not checked in the prototype') && res.includes('1 (not verified)'))
await page.getByRole('button', {name: 'The signed sample report'}).click()
await page.screenshot({path: `${out}/check-light.png`, fullPage: true})

// ---- Themes
await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))
await page.locator('.nav button', {hasText: 'Reports'}).click()
const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
const paperBg = await page.evaluate(() => getComputedStyle(document.querySelector('.sheet')).backgroundColor)
ok('dark theme applies, paper stays white', darkBg === 'rgb(11, 20, 32)' && paperBg === 'rgb(255, 255, 255)', `${darkBg} / ${paperBg}`)
await page.screenshot({path: `${out}/report-dark.png`, fullPage: true})
await page.locator('.nav button', {hasText: 'Templates'}).click()
await page.screenshot({path: `${out}/builder-dark.png`, fullPage: true})
const sys = await browser.newPage({viewport: {width: 1200, height: 900}, colorScheme: 'dark'})
await sys.goto(file + '#questions')
ok('the system dark setting applies', (await sys.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(11, 20, 32)')

// ---- Phone width: no horizontal page scroll anywhere
for (const width of [390, 360]) {
  const phone = await browser.newPage({viewport: {width, height: 800}, isMobile: true, hasTouch: true})
  for (const view of ['questions', 'layout', 'data', 'try', 'report', 'library', 'check']) {
    await phone.goto(file + '#' + view)
    await phone.waitForTimeout(150)
    await phone.evaluate(() => document.fonts.ready)
    if (view === 'check') await phone.getByRole('button', {name: 'The signed sample report'}).click()
    if (view === 'report') await phone.getByRole('button', {name: /Show the PDF/}).click()
    const [sw, cw, widest] = await phone.evaluate(() => {
      const cw = document.documentElement.clientWidth
      const widest = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > cw + 0.5)
        .map((e) => `${e.tagName.toLowerCase()}.${[...e.classList][0] ?? ''}`).slice(-3).join(', ')
      return [document.documentElement.scrollWidth, cw, widest]
    })
    ok(`phone width ${width}px, ${view}: no horizontal scroll`, sw <= cw, `${sw} > ${cw}: ${widest}`)
    if (width === 390) await phone.screenshot({path: `${out}/phone-${view}.png`, fullPage: true})
  }
}

ok('no network requests', requests.length === 0, requests.join(', '))
ok('no console errors or warnings', errors.length === 0, errors.join(' || '))
await browser.close()

for (const r of results) console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.pass || !r.detail ? '' : `  (${r.detail})`}`)
// In GitHub Actions, failures also become annotations, which show on the pull request without opening the log.
if (process.env.GITHUB_ACTIONS) {
  const clean = (s) => String(s).replace(/%/g, '%25').replace(/\r?\n/g, ' ').slice(0, 900)
  for (const r of results.filter((x) => !x.pass)) console.log(`::error title=Browser check failed::${clean(r.name)}${r.detail ? ` (${clean(r.detail)})` : ''}`)
}
console.log(`${results.filter((r) => r.pass).length} of ${results.length} checks passed`)
process.exitCode = results.every((r) => r.pass) ? 0 : 1
