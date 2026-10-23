// Browser checks for the built prototype: no errors or network requests, drag and drop, page breaks, rules,
// renaming, the CEL validator, both themes and phone width. Run with `npm run check:browser` after `npm run build`.
// Screenshots go to dist/shots.
import {chromium} from 'playwright'
import {mkdirSync} from 'node:fs'
import path from 'node:path'

const file = 'file://' + path.resolve('dist/index.html')
const out = 'dist/shots'
mkdirSync(out, {recursive: true})
const results = []
const ok = (name, cond, detail = '') => { results.push({name, pass: !!cond, detail}); }

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({viewport: {width: 1440, height: 1400}})
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`) })
  const requests = []
  page.on('request', (r) => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) requests.push(r.url()) })

  await page.goto(file + '#layout')
  await page.waitForSelector('.blocks .block')
  await page.evaluate(() => document.fonts.ready)
  ok('fonts loaded from the bundle', await page.evaluate(() => ['Marcellus', 'IBM Plex Sans', 'Mr Dafoe'].every((f) => document.fonts.check(`16px "${f}"`))))
  await page.screenshot({path: `${out}/layout-light.png`, fullPage: true})

  // Drag "Page break" from the palette to just above the "Actions taken" section.
  const before = await page.locator('.blocks .block').count()
  const src = page.locator('.palette .entry', {hasText: 'Page break'})
  const target = page.locator('.blocks .block', {hasText: 'Actions taken'}).first()
  const s = await src.boundingBox(); const t = await target.boundingBox()
  await page.mouse.move(s.x + 20, s.y + s.height / 2)
  await page.mouse.down()
  for (let i = 1; i <= 25; i++) await page.mouse.move(s.x + 20 + ((t.x + 60 - s.x - 20) * i) / 25, s.y + s.height / 2 + ((t.y + 8 - s.y - s.height / 2) * i) / 25)
  await page.waitForTimeout(300)
  await page.mouse.up()
  await page.waitForTimeout(400)
  const after = await page.locator('.blocks .block').count()
  const kinds = await page.locator('.blocks .block').evaluateAll((els) => els.map((e) => [...e.classList].find((c) => c.startsWith('kind-'))))
  ok('drag from the palette adds a block', after === before + 1, `${before} → ${after}`)
  ok('palette keeps its entries after a drag', (await page.locator('.palette .entry').count()) === 8)
  ok('dropped block becomes selected', (await page.locator('.props h2').textContent()).trim() === 'Page break')
  const pbIndex = kinds.indexOf('kind-pagebreak')
  ok('dropped where it was released', pbIndex > 0 && kinds[pbIndex + 1] === 'kind-section', kinds.join(','))

  // Reorder: drag the "Credentials found" heading up into section 2, above its first text block.
  const order = async () => page.locator('.blocks .block').evaluateAll((els) => els.map((e) => e.textContent.trim().slice(0, 24)))
  const h = await page.locator('.blocks .block', {hasText: 'Credentials found'}).boundingBox()
  const a = await page.locator('.blocks .block', {hasText: 'Traffic from these addresses'}).boundingBox()
  await page.mouse.move(h.x + 40, h.y + h.height / 2)
  await page.mouse.down()
  for (let i = 1; i <= 25; i++) await page.mouse.move(h.x + 40, h.y + h.height / 2 + ((a.y + 6 - h.y - h.height / 2) * i) / 25)
  await page.waitForTimeout(300)
  await page.mouse.up()
  await page.waitForTimeout(400)
  const reordered = await order()
  const ci = reordered.findIndex((t) => t.startsWith('Credentials found'))
  ok('blocks reorder by dragging', reordered[ci + 1]?.startsWith('Traffic from'), reordered.join(' | '))

  // Click-to-add adds after the selected block.
  await page.locator('.blocks .block', {hasText: 'Summary'}).first().locator('.pick').click()
  await page.locator('.palette .entry', {hasText: 'Callout'}).click()
  const kinds2 = await page.locator('.blocks .block').evaluateAll((els) => els.map((e) => [...e.classList].find((c) => c.startsWith('kind-'))))
  ok('click adds after the selected block', kinds2[1] === 'kind-callout', kinds2.slice(0, 3).join(','))
  await page.locator('.props .btn', {hasText: 'Remove'}).click()

  // Condition editor shows CEL.
  await page.locator('.blocks .block', {hasText: 'Attacking addresses'}).first().locator('.pick').click()
  ok('rule stored as CEL', (await page.locator('.props .cel code').textContent()).trim() === 'answers.attack_found == true')

  // Preview: page breaks with the drag-added break before "Actions taken" (no extra page, the section starts one anyway).
  await page.locator('[role=tab]', {hasText: 'Preview'}).click()
  await page.waitForSelector('.sheet')
  await page.evaluate(() => document.fonts.ready)
  const labels = await page.locator('.sheet h2.section').allTextContents()
  ok('4 pages with default answers', (await page.locator('.sheet').count()) === 4, labels.join(' | '))
  const perPage = await page.locator('.sheet').evaluateAll((els) => els.map((e) => [...e.querySelectorAll('h2.section')].map((h) => h.textContent.replace(/^\d+/, ''))))
  ok('each major section on its own page', JSON.stringify(perPage) === JSON.stringify([['Summary'], ['Attacking addresses'], ['Actions taken'], ['Sign-off']]), JSON.stringify(perPage))
  ok('secret is masked in the PDF preview', !(await page.locator('.sheets, .pages').textContent()).includes('Hunter2'))
  ok('page footer counts pages', (await page.locator('.sheet .run-foot').last().textContent()).includes('Page 4 of 4'))
  ok('no page flagged as too long', (await page.locator('.sheet.over').count()) === 0)
  await page.screenshot({path: `${out}/preview-light.png`, fullPage: true})

  // Answer "No" to the attack question: the section, its table and the repeating question disappear.
  await page.locator('fieldset.yesno', {hasText: 'attacking address'}).getByLabel('No').check()
  await page.waitForTimeout(100)
  ok('hidden section removes its page', (await page.locator('.sheet').count()) === 3)
  ok('conditional question hidden in the form', (await page.locator('fieldset.repeat').count()) === 0)
  ok('rule panel shows false', (await page.locator('.rules .pill', {hasText: 'False: hidden'}).count()) >= 2)
  await page.locator('fieldset.yesno', {hasText: 'attacking address'}).getByLabel('Yes').check()

  // CVSS below 7 hides the credentials blocks; severity recalculates.
  await page.getByLabel('Highest CVSS score *').fill('5')
  await page.waitForTimeout(100)
  ok('severity recalculated', (await page.locator('.sheet .callout').first().textContent()).includes('Medium'))
  ok('credentials blocks hidden below CVSS 7', (await page.locator('.sheet h3', {hasText: 'Credentials'}).count()) === 0)
  await page.getByLabel('Highest CVSS score *').fill('7.5')

  // A very long answer makes a page longer than A4 and is flagged.
  await page.getByLabel('Actions taken *').fill('Long text. '.repeat(900))
  await page.waitForTimeout(300)
  ok('page longer than A4 is flagged', (await page.locator('.sheet.over').count()) === 1)
  await page.getByLabel('Actions taken *').fill('Short again.')

  // Rename a variable on the Questions tab: blocks and rules follow.
  await page.locator('[role=tab]', {hasText: 'Questions'}).click()
  const qBefore = await page.locator('.cards .card').count()
  const ds = await page.locator('.palette .entry', {hasText: 'Dropdown'}).boundingBox()
  const dt = await page.locator('.cards .card', {hasText: 'Actions taken'}).boundingBox()
  await page.mouse.move(ds.x + 20, ds.y + ds.height / 2)
  await page.mouse.down()
  for (let i = 1; i <= 25; i++) await page.mouse.move(ds.x + 20 + ((dt.x + 80 - ds.x - 20) * i) / 25, ds.y + ds.height / 2 + ((dt.y + 10 - ds.y - ds.height / 2) * i) / 25)
  await page.waitForTimeout(300)
  await page.mouse.up()
  await page.waitForTimeout(400)
  ok('drag a field type into the form', (await page.locator('.cards .card').count()) === qBefore + 1 && (await page.locator('.props h2').textContent()).trim() === 'Dropdown')
  await page.locator('.props .btn', {hasText: 'Remove'}).click()
  await page.locator('.card', {hasText: 'Highest CVSS score'}).locator('.pick').click()
  await page.locator('#q-key').fill('cvss_score')
  await page.locator('#q-key').press('Enter')
  await page.locator('#q-key').blur()
  await page.locator('[role=tab]', {hasText: 'Preview'}).click()
  ok('renamed variable still fills the text', (await page.locator('.sheet .callout').first().textContent()).includes('CVSS 7.5'))
  ok('renamed variable still fills the cover', (await page.locator('.sheet .facts').first().textContent()).includes('High · CVSS 7.5'))
  ok('cover date formatted', (await page.locator('.sheet .facts').first().textContent()).includes('21 October 2026 at 03:14'))
  ok('renamed variable rules still work', (await page.locator('.rules code', {hasText: 'answers.cvss_score >= 7.0'}).count()) >= 1)
  await page.locator('[role=tab]', {hasText: 'Questions'}).click()
  await page.locator('.card', {hasText: 'Highest CVSS score'}).locator('.pick').click()
  await page.locator('#q-key').fill('Bad Name')
  await page.locator('#q-key').press('Enter')
  ok('invalid variable name refused', (await page.locator('.props .error').count()) === 1)
  await page.screenshot({path: `${out}/questions-light.png`, fullPage: true})

  // Data tab: playground and the banned matches().
  await page.locator('[role=tab]', {hasText: 'Data'}).click()
  await page.locator('.examples .btn', {hasText: 'Rejected'}).click()
  ok('matches() rejected in the playground', (await page.locator('.outcome').textContent()).includes('not allowed'))
  await page.locator('.examples .btn', {hasText: 'Lookup'}).click()
  ok('lookup works', (await page.locator('.outcome').textContent()).includes('Høj'))
  await page.screenshot({path: `${out}/data-light.png`, fullPage: true})

  // Dark theme via the viewer's attribute, and via the system setting.
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'))
  await page.locator('[role=tab]', {hasText: 'Preview'}).click()
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  const paperBg = await page.evaluate(() => getComputedStyle(document.querySelector('.sheet')).backgroundColor)
  ok('dark theme applies, paper stays white', darkBg === 'rgb(11, 20, 32)' && paperBg === 'rgb(255, 255, 255)', `${darkBg} / ${paperBg}`)
  await page.screenshot({path: `${out}/preview-dark.png`, fullPage: true})
  await page.locator('[role=tab]', {hasText: 'Layout'}).click()
  await page.screenshot({path: `${out}/layout-dark.png`, fullPage: true})

  const sys = await browser.newPage({viewport: {width: 1200, height: 900}, colorScheme: 'dark'})
  await sys.goto(file + '#questions')
  ok('system dark preference applies', (await sys.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(11, 20, 32)')

  // Phone width: no horizontal page scroll on any tab.
  for (const width of [390, 360]) {
    const phone = await browser.newPage({viewport: {width, height: 800}, isMobile: true, hasTouch: true})
    for (const tab of ['questions', 'layout', 'data', 'preview']) {
      await phone.goto(file + '#' + tab)
      await phone.waitForTimeout(150)
      await phone.evaluate(() => document.fonts.ready)
      const [sw, cw, widest] = await phone.evaluate(() => {
        const cw = document.documentElement.clientWidth
        const widest = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > cw + 0.5)
          .map((e) => `${e.tagName.toLowerCase()}.${[...e.classList][0] ?? ''}`).slice(-3).join(', ')
        return [document.documentElement.scrollWidth, cw, widest]
      })
      ok(`phone width ${width}px, ${tab}: no horizontal scroll`, sw <= cw, `${sw} > ${cw}: ${widest}`)
      if (width === 390) await phone.screenshot({path: `${out}/phone-${tab}.png`, fullPage: true})
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
  process.exitCode = results.every((r) => r.pass) ? 0 : 1
})()
