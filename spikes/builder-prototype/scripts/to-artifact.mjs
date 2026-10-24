// Turns dist/index.html into a page fragment for a claude.ai Artifact (the host adds doctype, head and body),
// and checks that the build fetches nothing from the network. The HTML is parsed with parse5, not regular
// expressions, so tags in any letter case and odd markup are handled the way a browser handles them.
import {readFileSync, writeFileSync} from 'node:fs'
import {parse, serializeOuter} from 'parse5'

const document = parse(readFileSync('dist/index.html', 'utf8'))

const elements = (node) => (node.childNodes ?? []).filter((n) => n.tagName)
const find = (node, tag) => elements(node).find((n) => n.tagName === tag)
const html = find(document, 'html')
const head = find(html, 'head')
const body = find(html, 'body')
const attr = (node, name) => node.attrs?.find((a) => a.name === name)?.value

const headParts = elements(head)
const title = headParts.filter((n) => n.tagName === 'title')
const metas = headParts.filter((n) => n.tagName === 'meta' && attr(n, 'name')?.startsWith('claude:'))
const styles = headParts.filter((n) => n.tagName === 'style')
const scripts = [...headParts, ...elements(body)].filter((n) => n.tagName === 'script')
const content = elements(body).filter((n) => n.tagName !== 'script')

// Everything the page needs must be inline: no script, stylesheet or image may come from elsewhere.
const external = []
const walk = (node) => {
  for (const name of ['src', 'href']) {
    const value = attr(node, name)
    if (value && !value.startsWith('data:') && !value.startsWith('#')) external.push(`${node.tagName} ${name}="${value}"`)
  }
  for (const child of node.childNodes ?? []) walk(child)
}
walk(html)
if (external.length) throw new Error(`The build references outside resources: ${external.join(', ')}`)
if (!content.some((n) => attr(n, 'id') === 'app')) throw new Error('The mount point <div id="app"> is missing')

const fragment = [...title, ...metas, ...styles, ...content, ...scripts].map((n) => serializeOuter(n)).join('\n')
writeFileSync('dist/artifact.html', fragment)
console.log(`dist/artifact.html: ${(fragment.length / 1024).toFixed(0)} KiB, ${scripts.length} script, ${styles.length} style`)
