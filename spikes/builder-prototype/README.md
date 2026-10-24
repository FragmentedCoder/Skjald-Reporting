# Spike: template builder prototype

**Result: the builder's approach works, and the second round makes clear who sees what.** Svelte 5 with svelte-dnd-action handles dragging from a palette, reordering and click-to-add. Rules are stored as CEL and evaluated live. The preview breaks pages the same way the PDF renderer does. The whole prototype is one self-contained HTML file that makes no network requests.

This is a throwaway proof of concept for Phase 0, not the start of the real frontend; the real builder is built in Phase 2. Nothing is saved, and the sample data is fictional (Nordlys IT ApS and Fjordvik Logistik A/S).

## What it shows

Switch **Viewing as** at the top to see each role's screens. Technicians get Reports, the Library and Check a report; Templates is only for report designers and administrators.

| Screen | Who | What you can do |
| --- | --- | --- |
| Templates › Questions | Designers, admins | Build the form the technician fills in: form steps, questions, help text, dropdown options, table columns, secret settings. Each card says whether and where the answer is printed. Renaming a variable updates every block, rule, cover fact and calculated value that uses it. |
| Templates › Layout | Designers, admins | Build the PDF from blocks: section, heading, text, answer, table, image, callout, sources, page break, signatures. Every block has its own settings (see below) and an optional rule. |
| Templates › Data | Designers, admins | Every name a template can read, what it is, where it comes from and a worked example; calculated values; a reference for every function with a live result; a box to try expressions. |
| Templates › Try it | Designers, admins | The technician's screen with the sample answers, so the template can be tested before it is published. |
| Reports | Everyone | The technician's screen: the form one step at a time, with the PDF next to it, updating as you type. Secrets are revealed with an MFA code for 30 seconds. Review lists what is missing. |
| Library | Everyone | Shared variables, text snippets and data tables. Anyone can add and change entries; every change is logged, and administrators can lock an entry. |
| Check a report | Everyone | Upload a signed PDF to see whether it is genuine and unchanged. The two samples show real results from `spikes/pdf-signing/check_report.py`. |

Everything is labelled with where it shows up: **Form** (the technician sees it), **PDF** (printed for the customer) or **Builder only**.

### Block settings

| Block | Settings |
| --- | --- |
| Section | Title, introduction printed under the heading, start on a new page (on by default), numbered or not |
| Table | Rows from a repeating group, caption ("Table 1. …", numbered automatically), which columns and in what order, text when there are no rows |
| Image | A file uploaded with the template or a photo the technician adds, caption ("Figure 1. …"), width |
| Callout | A named tone from the style (Info, Note, Warning, Critical, Success) or a custom colour, with a contrast check; title and text |
| Sources | Sources every report gets, plus the technician's own from a repeating group; printed as a numbered list |
| Signatures | One to four boxes; who signs each, handwritten or stamp, label; side by side or stacked; signing date |
| Text, heading, answer | Text with variables and library snippets; which answer, with or without its question |

## Findings

- **Separate the form from the PDF in the builder.** The first round mixed them, and it was hard to tell what the technician sees from what the customer gets. Now the Questions tab is the form, the Layout tab is the PDF, every element is tagged Form, PDF or Builder only, and each question shows where it is printed.
- **Secrets are printed partly, never in full.** At most a quarter of the characters, at most three at each end, and a fixed run of dots so the length isn't given away: `Hunter2-portal-admin` prints as `Hu••••••in`, `Summer26` as `S••••••6`. A template can also leave the secret out. Technicians reveal the full value in the app with an MFA code; every reveal is logged.
- **Text snippets may use variables, but not other snippets**, so a snippet can't loop. Library edits take effect for new reports; signed reports keep the values they were signed with.
- **Custom colours need a contrast check.** The text colour is picked automatically (Midnat or white), and the builder warns below 4.5:1 (WCAG AA).
- **Images are capped at about 40% of the page height**, so a tall or square photo can't push a page over.
- **svelte-dnd-action works with Svelte 5.** The palette uses its copy-on-drag pattern. Each zone type (blocks, questions) is separate, so blocks can't land in the question list.
- **Drags don't start on elements that have a `value`, and buttons do.** svelte-dnd-action skips presses on form fields, and a `<button>` counts. Every draggable button has a span inside it that takes the press; the browser checks cover this, because it fails silently.
- **Visual rules map cleanly to CEL**, including "is filled in" and "is empty". Every question gets a default value, so rules never fail on a missing answer.
- **A tall page must not widen itself.** An element with `aspect-ratio` takes a minimum width from its height; `min-width: 0` makes it grow taller instead.

## What's left for the real builder

- Evaluate expressions in a Web Worker with a time limit, as the architecture says. The prototype evaluates on the main thread.
- Nested sections, columns, the header, footer and background designer, and the table of contents.
- Keyboard reordering uses svelte-dnd-action's built-in mode (focus a block, press Space, move with the arrow keys). It needs testing with a screen reader.
- Check a report: the prototype can only hash an uploaded file and count its signatures; the real check runs on the server.

## Run it

```sh
npm ci
npm test               # pagination, variables, secrets, colours and CEL (Node)
npm run build          # dist/index.html, plus dist/artifact.html as a page fragment
npm run check:browser  # 80 checks in Chromium, screenshots in dist/shots
npm run dev            # live development server
```

`npm run check:browser` needs Playwright's Chromium (`npx playwright install chromium`).
