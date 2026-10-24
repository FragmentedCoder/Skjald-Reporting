// Turns dist/index.html into a page fragment for a claude.ai Artifact (the host adds doctype, head and body),
// and checks that the build fetches nothing from the network.
import {readFileSync, writeFileSync} from 'node:fs'

const html = readFileSync('dist/index.html', 'utf8')
const pick = (re) => [...html.matchAll(re)].map((m) => m[0])

const title = pick(/<title>[\s\S]*?<\/title>/g)
const metas = pick(/<meta name="claude:[^>]*>/g)
const styles = pick(/<style[\s\S]*?<\/style>/g)
const scripts = pick(/<script[\s\S]*?<\/script>/g)
const body = html.match(/<body>([\s\S]*?)<\/body>/)?.[1].replace(/<script[\s\S]*?<\/script>/g, '').trim() ?? ''

const fragment = [...title, ...metas, ...styles, body, ...scripts].join('\n')

const external = fragment.match(/(?:src|href)=["']https?:\/\/[^"']+/g)
if (external) throw new Error(`The build references external resources: ${external.join(', ')}`)
if (!fragment.includes('<div id="app">')) throw new Error('Mount point missing from the fragment')

writeFileSync('dist/artifact.html', fragment)
console.log(`dist/artifact.html: ${(fragment.length / 1024).toFixed(0)} KiB, ${scripts.length} script, ${styles.length} style`)
