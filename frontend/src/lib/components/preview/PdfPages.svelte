<script lang="ts" module>
  import { contrast } from "#lib/colours.js";

  /** The text colour for a custom fill: Midnat or white, whichever reads better. */
  export function inkFor(fill: string): { ink: string; ratio: number } {
    const dark = contrast("#0F1B2D", fill);
    const light = contrast("#FFFFFF", fill);
    return dark >= light ? { ink: "#0F1B2D", ratio: dark } : { ink: "#FFFFFF", ratio: light };
  }
</script>

<script lang="ts">
  import { onMount, tick } from "svelte";
  import type { Paged, Placed } from "#lib/templates/pages.js";
  import type { Grid, Shown } from "#lib/templates/preview.js";
  import RichView from "./RichView.svelte";

  // The PDF's pages, as A4 sheets that scale with the space they have. The page rules
  // (pages.ts) decide what goes on which page; exact pagination is the renderer's job,
  // so a page whose content runs over is flagged, not split. Drawn in the report's
  // colours whatever the app's theme. A page's header and footer carry the report
  // number, the classification and "Page X of Y"; DRAFT runs across every page until
  // the report is signed.
  let {
    paged,
    reportNumber = "INC-2026-0142",
    classification = "TLP:AMBER",
    company = "Nordlys IT ApS",
    selected = null,
    onselect,
  }: {
    paged: Paged;
    reportNumber?: string;
    classification?: string;
    company?: string;
    selected?: string | null;
    onselect?: (id: string) => void;
  } = $props();

  let sheets = $state<HTMLElement[]>([]);
  let over = $state<boolean[]>([]);

  // A page whose content is taller than the page: the PDF carries it onto the next.
  async function measure() {
    await tick();
    over = sheets.map((sheet) => {
      const body = sheet?.querySelector<HTMLElement>(".body");
      return !!body && body.scrollHeight > body.clientHeight + 2;
    });
  }

  $effect(() => {
    void paged;
    void measure();
  });

  onMount(() => {
    const observer = new ResizeObserver(() => void measure());
    for (const sheet of sheets) if (sheet) observer.observe(sheet);
    return () => observer.disconnect();
  });

  const total = $derived(paged.pages.length);
  const base = (id: string) => id.split("~")[0];

  // Clicking a block on a page chooses it: a shortcut for the mouse, beside the
  // outline, which is the way to choose one with the keyboard.
  function choose(node: HTMLElement) {
    const click = (event: MouseEvent) => {
      const block = (event.target as HTMLElement).closest<HTMLElement>("[data-block]");
      if (block?.dataset.block && onselect) onselect(block.dataset.block);
    };
    node.addEventListener("click", click);
    return { destroy: () => node.removeEventListener("click", click) };
  }

  function paint(node: HTMLElement, colour: string | null) {
    const apply = (value: string | null) => {
      if (value) {
        node.style.setProperty("--fill", value);
        node.style.setProperty("--ink", inkFor(value).ink);
      } else {
        node.style.removeProperty("--fill");
        node.style.removeProperty("--ink");
      }
    };
    apply(colour);
    return { update: apply };
  }

  function widthOf(node: HTMLElement, settings: { width: string; ratio: number }) {
    const apply = (s: { width: string; ratio: number }) => {
      const share = { full: 100, two_thirds: 66.7, half: 50, third: 33.3 }[s.width] ?? 100;
      // At most about 40% of the page's height.
      const most = (0.4 * 297) / 210 / Math.max(s.ratio, 0.01) * 100;
      node.style.setProperty("--share", `${Math.min(share, most)}%`);
      node.style.setProperty("--ratio", String(s.ratio));
    };
    apply(settings);
    return { update: apply };
  }
</script>

{#snippet grid(g: Grid, empty = "")}
  {#if g.rows.length}
    <table>
      <thead><tr>{#each g.headers as h, i (i)}<th>{h}</th>{/each}</tr></thead>
      <tbody>{#each g.rows as row, r (r)}<tr>{#each row as cell, c (c)}<td>{cell}</td>{/each}</tr>{/each}</tbody>
    </table>
  {:else}
    <p class="muted">{empty}</p>
  {/if}
{/snippet}

{#snippet block(b: Shown, placed: Placed | null)}
  {#if b.kind === "cover"}
    <div class="cover">
      {#if b.showLogo}<div class="logo" aria-hidden="true">{company}</div>{/if}
      <p class="overline">{reportNumber}</p>
      <h1>{b.title}</h1>
      {#if b.subtitle}<p class="subtitle">{b.subtitle}</p>{/if}
      {#if b.facts.length}
        <dl class="facts">{#each b.facts as fact, i (i)}<dt>{fact.label}</dt><dd>{fact.value}</dd>{/each}</dl>
      {/if}
    </div>
  {:else if b.kind === "toc"}
    <div class="toc">
      <h2>{b.title}</h2>
      <ol>
        {#each paged.contents.filter((c) => c.depth < b.depth) as entry, i (i)}
          <li class="depth-{entry.depth}"><span>{entry.number ? `${entry.number} ` : ""}{entry.title}</span><span class="dots"></span><span>{entry.page}</span></li>
        {/each}
      </ol>
    </div>
  {:else if b.kind === "section"}
    <h2 class="section-heading depth-{placed?.depth ?? 0}">{placed?.number ? `${placed.number} ` : ""}{b.title}</h2>
    {#if b.intro}<div class="intro"><RichView nodes={b.intro.content} /></div>{/if}
  {:else if b.kind === "heading"}
    <h3>{b.text}</h3>
  {:else if b.kind === "text"}
    <RichView nodes={b.content.content} />
  {:else if b.kind === "answer"}
    <div class="answer">
      {#if b.label}<p class="question">{b.label}</p>{/if}
      {#if b.rich}<RichView nodes={b.rich.content} />{:else if b.rows}{@render grid(b.rows)}{:else}<p>{b.text || "—"}</p>{/if}
    </div>
  {:else if b.kind === "table"}
    <figure class="grid-figure">
      {#if placed?.caption}<figcaption>{placed.caption}{b.caption ? `. ${b.caption}` : ""}</figcaption>{/if}
      {@render grid(b.grid, b.emptyText)}
    </figure>
  {:else if b.kind === "image"}
    <figure class="image" use:widthOf={{ width: b.width, ratio: b.ratio }}>
      {#if b.url}<img src={b.url} alt={b.caption} />{:else}<div class="placeholder">The technician's photo goes here</div>{/if}
      {#if placed?.caption}<figcaption>{placed.caption}{b.caption ? `. ${b.caption}` : ""}</figcaption>{/if}
    </figure>
  {:else if b.kind === "gallery"}
    <figure class="gallery per-{b.perRow}">
      <div class="photos">
        {#each b.urls.length ? b.urls : [null, null] as url, i (i)}
          {#if url}<img src={url} alt="Photo {i + 1}" />{:else}<div class="placeholder">Photo {i + 1}</div>{/if}
        {/each}
      </div>
      {#if placed?.caption}<figcaption>{placed.caption}{b.caption ? `. ${b.caption}` : ""}</figcaption>{/if}
    </figure>
  {:else if b.kind === "callout"}
    <aside class="callout tone-{b.tone}" use:paint={b.tone === "custom" ? b.colour : null}>
      {#if b.title}<p class="callout-title">{b.title}</p>{/if}
      <RichView nodes={b.content.content} />
    </aside>
  {:else if b.kind === "severity_summary"}
    <figure class="severity">
      <div class="counts">{#each b.counts as c (c.level)}<div class="count"><span class="n">{c.count}</span><span>{c.level}</span></div>{/each}</div>
      {#if b.caption}<figcaption>{b.caption}</figcaption>{/if}
    </figure>
  {:else if b.kind === "sources"}
    <div class="sources">
      {#if b.intro}<p>{b.intro}</p>{/if}
      <ol>{#each b.items as item, i (i)}<li>{item.title}{#if item.link} <span class="link">{item.link}</span>{/if}</li>{/each}</ol>
    </div>
  {:else if b.kind === "signatures"}
    <div class="signatures {b.layout}">
      {#each b.signers as signer, i (i)}
        <div class="signature">
          <div class="line" class:stamp={signer.style === "stamp"}>{signer.style === "stamp" ? company : ""}</div>
          <p class="question">{signer.label}</p>
          {#if b.showDate}<p class="muted">Date of signing</p>{/if}
        </div>
      {/each}
    </div>
  {:else if b.kind === "columns"}
    <div class="columns">
      {#each b.columns as column, i (i)}<div class="column">{#each column as inner (inner.id)}{@render item(inner, null)}{/each}</div>{/each}
    </div>
  {/if}
{/snippet}

{#snippet item(b: Shown, placed: Placed | null)}
  <div class="item" class:chosen={selected !== null && base(b.id) === selected} data-block={base(b.id)}>
    {@render block(b, placed)}
  </div>
{/snippet}

<div class="pages" class:choosing={!!onselect} aria-label="The PDF's pages, with the sample answers" use:choose>
  {#each paged.pages as page, p (p)}
    <section class="sheet {page.orientation}" class:cover={page.cover} bind:this={sheets[p]} aria-label="Page {p + 1} of {total}">
      <div class="paper">
        {#if !page.cover}
          <header class="running"><span>{company}</span><span class="classification">{classification}</span></header>
        {/if}
        <div class="body">
          {#each page.items as placed, i (i)}{@render item(placed.block, placed)}{/each}
        </div>
        <footer class="running"><span>{reportNumber}</span><span>Page {p + 1} of {total}</span></footer>
        <div class="watermark" aria-hidden="true">DRAFT</div>
      </div>
      <p class="why small">
        Page {p + 1}: {page.reason}{#if over[p]}<span class="over"> · runs over: the PDF continues it on the next page</span>{/if}
      </p>
    </section>
  {:else}
    <p class="muted">Nothing is printed yet: add blocks, or check the rules that hide them.</p>
  {/each}
</div>

<style>
  .pages {
    display: grid;
    gap: var(--space-4);
    justify-items: center;
  }
  .sheet {
    width: 100%;
    max-width: 794px;
  }
  .sheet.landscape {
    max-width: 1123px;
  }
  /* The report's own colours (docs/brand/tokens.json, light), whatever the app's theme. */
  .paper {
    --paper: #ffffff;
    --text-ink: #0f1b2d;
    --text-soft: #5b6675;
    --rule: #e5e5e5;
    --subtle: #efefef;
    position: relative;
    container-type: inline-size;
    aspect-ratio: 210 / 297;
    overflow: hidden;
    border: 1px solid var(--border);
    background: var(--paper);
    color: var(--text-ink);
    font-family: var(--font-sans);
  }
  .landscape .paper {
    aspect-ratio: 297 / 210;
  }
  .running,
  .body {
    position: absolute;
    left: 6.05cqi;
    right: 6.05cqi;
    /* 15 px body text on an A4 page 794 px wide, scaled with the page. */
    font-size: 1.889cqi;
  }
  .landscape .running,
  .landscape .body {
    font-size: 1.336cqi;
    left: 4.27cqi;
    right: 4.27cqi;
  }
  .running {
    display: flex;
    justify-content: space-between;
    color: var(--text-soft);
    font-size: 1.3cqi;
  }
  .landscape .running {
    font-size: 0.92cqi;
  }
  header.running {
    top: 3cqi;
  }
  footer.running {
    bottom: 3cqi;
  }
  .classification {
    font-weight: 600;
    color: #8a5a12;
  }
  .body {
    top: 7cqi;
    bottom: 7cqi;
    overflow: hidden;
    line-height: 1.6;
  }
  .cover .body {
    top: 6.05cqi;
  }
  .watermark {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: rgb(15 27 45 / 0.06);
    font-family: var(--font-display);
    font-size: 22cqi;
    pointer-events: none;
    rotate: -30deg;
  }
  .why {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
  }
  .over {
    color: var(--warning-text);
    font-weight: 600;
  }
  .item {
    border-radius: 0.2em;
    outline-offset: 0.15em;
  }
  .choosing .item:hover {
    outline: 1px dashed var(--link);
    cursor: pointer;
  }
  .item.chosen {
    outline: 2px solid var(--link);
  }
  .body :global(p) {
    margin: 0 0 0.6em;
  }
  .body :global(ul),
  .body :global(ol) {
    margin: 0 0 0.6em;
    padding-left: 1.4em;
  }
  .body :global(code) {
    font-family: var(--font-mono);
    font-size: 0.87em;
  }
  .body :global(a) {
    color: #2b5d8a;
  }
  h1,
  h2,
  h3,
  .body :global(h3),
  .body :global(h4) {
    margin: 0.8em 0 0.4em;
    font-family: var(--font-display);
    font-weight: 400;
    line-height: 1.2;
  }
  h1 {
    font-size: 2.67em;
  }
  .section-heading {
    font-size: 1.87em;
  }
  .section-heading.depth-1,
  .section-heading.depth-2 {
    font-size: 1.47em;
  }
  h3,
  .body :global(h3) {
    font-size: 1.2em;
  }
  .body :global(h4) {
    font-size: 1.07em;
  }
  .overline {
    margin: 0;
    color: var(--text-soft);
    font-size: 0.8em;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .cover {
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 100%;
    padding-top: 30%;
  }
  .cover h1 {
    margin-top: 0.2em;
  }
  .logo {
    position: absolute;
    top: 0;
    left: 0;
    padding: 0.3em 0.6em;
    border: 1px solid var(--rule);
    border-radius: 0.3em;
    font-family: var(--font-display);
  }
  .subtitle {
    color: var(--text-soft);
    font-size: 1.33em;
  }
  .facts {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.3em 1.2em;
    margin: 2em 0 0;
  }
  .facts dt {
    color: var(--text-soft);
  }
  .facts dd {
    margin: 0;
  }
  .toc ol {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .toc li {
    display: flex;
    gap: 0.4em;
  }
  .toc li.depth-1 {
    padding-left: 1.4em;
  }
  .toc .dots {
    flex: 1;
    border-bottom: 1px dotted var(--rule);
    margin-bottom: 0.45em;
  }
  .intro {
    color: var(--text-soft);
  }
  .question {
    margin-bottom: 0.2em;
    font-weight: 600;
  }
  figure {
    margin: 0 0 1em;
  }
  figcaption {
    margin-top: 0.3em;
    color: var(--text-soft);
    font-size: 0.87em;
  }
  .grid-figure figcaption {
    margin: 0 0 0.3em;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.87em;
  }
  th,
  td {
    padding: 0.35em 0.5em;
    border-bottom: 1px solid var(--rule);
    text-align: left;
  }
  th {
    background: var(--subtle);
    font-weight: 600;
  }
  .image {
    width: var(--share, 100%);
  }
  .image img,
  .gallery img {
    display: block;
    width: 100%;
    height: auto;
  }
  .placeholder {
    display: grid;
    place-items: center;
    aspect-ratio: 4 / 3;
    border: 1px dashed var(--rule);
    color: var(--text-soft);
    font-size: 0.87em;
  }
  .photos {
    display: grid;
    gap: 0.5em;
    grid-template-columns: repeat(2, 1fr);
  }
  .per-3 .photos {
    grid-template-columns: repeat(3, 1fr);
  }
  .callout {
    margin: 0 0 1em;
    padding: 0.8em 1em;
    border-radius: 0.4em;
    background: var(--fill, #dce6ee);
    color: var(--ink, #234c72);
  }
  .callout :global(p:last-child) {
    margin-bottom: 0;
  }
  .tone-note {
    --fill: #efefef;
    --ink: #0f1b2d;
  }
  .tone-warning {
    --fill: #fbefd9;
    --ink: #8a5a12;
  }
  .tone-critical {
    --fill: #f9e3e0;
    --ink: #a3352a;
  }
  .tone-success {
    --fill: #e3f1e8;
    --ink: #2f6b47;
  }
  .callout-title {
    font-weight: 600;
  }
  .counts {
    display: flex;
    gap: 0.6em;
  }
  .count {
    display: grid;
    flex: 1;
    padding: 0.5em;
    border: 1px solid var(--rule);
    border-radius: 0.4em;
    text-align: center;
  }
  .count .n {
    font-family: var(--font-display);
    font-size: 1.6em;
  }
  .sources .link {
    color: var(--text-soft);
    font-family: var(--font-mono);
    font-size: 0.8em;
    overflow-wrap: anywhere;
  }
  .signatures {
    display: flex;
    gap: 1.5em;
    margin-top: 1.5em;
  }
  .signatures.stack {
    flex-direction: column;
  }
  .signature {
    flex: 1;
  }
  .signature .line {
    height: 3em;
    border-bottom: 1px solid var(--text-ink);
  }
  .signature .line.stamp {
    display: grid;
    place-items: center;
    border: 1px solid var(--text-soft);
    border-radius: 50%;
    width: 5em;
    height: 5em;
    color: var(--text-soft);
    font-size: 0.7em;
    text-align: center;
  }
  .columns {
    display: flex;
    gap: 1.2em;
  }
  .column {
    flex: 1;
    min-width: 0;
  }
  .muted {
    color: var(--text-soft);
  }
</style>
