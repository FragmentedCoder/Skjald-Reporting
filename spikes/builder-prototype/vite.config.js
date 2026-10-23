import {defineConfig} from 'vite'
import {svelte} from '@sveltejs/vite-plugin-svelte'
import {viteSingleFile} from 'vite-plugin-singlefile'

// One self-contained HTML file: scripts, styles and fonts are all inlined, nothing is fetched at runtime.
export default defineConfig({
  plugins: [svelte(), viteSingleFile()],
  build: {target: 'es2022'},
})
