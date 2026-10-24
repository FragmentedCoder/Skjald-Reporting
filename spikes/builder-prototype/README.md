# Spike: drag-and-drop template builder

**Result: the builder's approach works.** Svelte 5 with svelte-dnd-action handles drag from a palette, reordering and click-to-add. Visual "show only when" rules are stored as CEL and evaluated live in the browser. The preview breaks pages the same way the PDF renderer does. The result is one self-contained HTML file that makes no network requests.

This is a throwaway prototype for phase 0, not the start of the real frontend. Nothing is saved; the sample data is fictional (Nordlys IT ApS and Fjordvik Logistik A/S).

## What it shows

| Tab | What you can do |
| --- | --- |
| Questions | Drag field types into the form, reorder questions, set labels, help text, dropdown options and table columns. Renaming a variable updates every block, rule, cover fact and calculated value that uses it. Invalid or duplicate names are refused. |
| Layout | Drag blocks onto the page (section, heading, text with `{{variables}}`, answer, table, callout, page break, signatures) and reorder them. Sections have **Start on a new page**, on by default. Any block or section can have a rule. |
| Data | Context from the customer and project, the sample answers, calculated values written in CEL, a lookup table, and a playground with examples of XOR, SWITCH, regex, text replacement, lookups and sums. |
| Preview | Edit the sample answers and watch the A4 pages change: hidden sections take their pages with them, the page count and "Page X of Y" update, secrets stay masked, and a page longer than A4 is flagged. A rules panel lists each rule, its CEL and whether it is true. |

## Findings

- **svelte-dnd-action works with Svelte 5.** The palette uses its copy-on-drag pattern: on `DRAG_STARTED` the dragged entry is put back with a new id, and the zone has `dropFromOthersDisabled`. Each zone type (blocks, questions) is a separate `type`, so blocks cannot land in the question list.
- **Drags don't start on elements that have a `value`, and buttons do.** svelte-dnd-action skips any press on an element with a `value` property, to avoid hijacking form fields. Buttons have one, so a drag that starts on a button never begins. Every draggable button here has a span inside it that takes the press. The browser checks cover this, because it fails silently.
- **Visual rules map cleanly to CEL.** The rule editor stores `{field, op, value}` and generates the CEL that would be saved, e.g. `answers.cvss >= 7.0` (numbers are written as decimals, because CEL treats `7` and `7.0` as different types). Advanced users can write CEL directly in calculated values.
- **The template validator is small.** cel-js parses an expression into an AST, and walking it for calls to `matches` is enough to reject the built-in regex function. Expressions are capped at 2,000 characters.
- **Pagination rules are simple enough to share.** `src/lib/pages.js` splits blocks into pages: a visible section with **Start on a new page** begins a page, a page-break block forces one, and nothing creates an empty page. The real renderer gets the same rules as CSS (`break-before: page`), and WeasyPrint flows long content onto extra pages. The preview only flags pages that overflow, because exact line-level pagination belongs to the renderer.
- **A tall page must not widen itself.** An element with `aspect-ratio` gets a minimum width from its height, so a page with lots of text pushed itself wider instead of longer. `min-width: 0` on the page fixes it.
- **Fonts can be bundled.** The build inlines the woff2 files from Fontsource, as the brand rules require; nothing loads from a font CDN. The whole page, including fonts, is about 540 KiB.

## What's left for the real builder

- Evaluate expressions in a Web Worker with a time limit, as the architecture says. The prototype evaluates on the main thread, which is fine with RE2 and 2,000-character expressions, but untrusted templates should not share a thread with the UI.
- Nested sections, columns, images, and the header, footer and background designer.
- Keyboard reordering is svelte-dnd-action's built-in mode (focus a block, press Space, move with the arrow keys). It needs testing with a screen reader before release.
- On phones the properties panel sits below the page. The builder is meant for desktop; filling in reports must work on phones, building templates only needs to be usable.

## Run it

```sh
npm ci
npm test               # pagination, variables and CEL rules (Node)
npm run build          # dist/index.html, plus dist/artifact.html as a page fragment
npm run check:browser  # 39 checks in Chromium, screenshots in dist/shots
npm run dev            # live development server
```

`npm run check:browser` needs Playwright's Chromium (`npx playwright install chromium`).
