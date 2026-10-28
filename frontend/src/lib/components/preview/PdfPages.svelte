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
  import { FONT_STACKS, plainLook, pointsToCqi, textKey, type PageLook } from "#lib/reportStyles/look.js";
  import { colourOf, TONE_NAMES, type Element, type PageName } from "#lib/reportStyles/resolve.js";
  import type { Paged, Placed } from "#lib/templates/pages.js";
  import type { Grid, Shown } from "#lib/templates/preview.js";
  import RichView from "./RichView.svelte";

  // The PDF's pages, as A4 sheets that scale with the space they have. The page rules
  // (pages.ts) decide what goes on which page; exact pagination is the renderer's job,
  // so a page whose content runs over is flagged, not split. Drawn in the report's
  // style (its colours, fonts, margins and page designs) whatever the app's theme: the
  // cover's design on the cover, the first page's on the first page after it, the other
  // pages' on the rest, each placing the logos, the report number, the classification
  // and "Page X of Y" around the text. The art behind the report's first page and behind
  // the rest comes from the customer's background or the style. DRAFT runs across every
  // page until the report is signed.
  let {
    paged,
    look = plainLook(),
    reportNumber = "INC-2026-0142",
    classification = "TLP:AMBER",
    company = "Nordlys IT ApS",
    language = "en",
    selected = null,
    onselect,
  }: {
    paged: Paged;
    look?: PageLook;
    reportNumber?: string;
    classification?: string;
    company?: string;
    language?: "en" | "da";
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

  // Who signs in the sample, and when: in the PDF, the signers' own signatures.
  const SAMPLE_SIGNERS = { technician: "Freja Holm", reviewer: "Ivar Lund" } as const;
  const signedOn = $derived(
    new Intl.DateTimeFormat(language === "da" ? "da-DK" : "en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date("2026-10-24T09:30:00Z")),
  );

  const total = $derived(paged.pages.length);
  const base = (id: string) => id.split("~")[0];

  // Which page design a sheet carries: the cover's, the first page's (the first sheet
  // after any cover) or the other pages'.
  const firstBody = $derived(paged.pages.findIndex((page) => !page.cover));
  function designOf(index: number): PageName {
    return paged.pages[index].cover ? "cover" : index === firstBody ? "first" : "other";
  }

  function pageNumber(index: number): string {
    return language === "da" ? `Side ${index + 1} af ${total}` : `Page ${index + 1} of ${total}`;
  }

  function words(e: Element, page: PageName, index: number): string {
    switch (e.kind) {
      case "text":
        return look.texts[textKey(page, e.id)] ?? e.text;
      case "page_number":
        return pageNumber(index);
      case "classification":
        return classification;
      case "report_number":
        return reportNumber;
      default:
        return "";
    }
  }

  // The style's values as custom properties on the pages, set through the CSSOM so the
  // strict Content-Security-Policy needs no inline styles.
  function dress(node: HTMLElement, current: PageLook) {
    const apply = (l: PageLook) => {
      const { style } = l;
      const set = (name: string, value: string) => node.style.setProperty(name, value);
      set("--r-text", style.colours.text);
      set("--r-muted", style.colours.muted);
      set("--r-heading", style.colours.heading);
      set("--r-accent", style.colours.accent);
      set("--r-link", style.colours.link);
      set("--r-line", style.colours.line);
      set("--r-head", style.colours.table_head);
      set("--r-head-ink", style.colours.table_head_text);
      set("--r-classification", style.colours.classification);
      for (const tone of TONE_NAMES) {
        set(`--r-${tone}-fill`, style.tones[tone].fill);
        set(`--r-${tone}-ink`, style.tones[tone].ink);
      }
      set("--r-font-heading", FONT_STACKS[style.fonts.heading]);
      set("--r-font-body", FONT_STACKS[style.fonts.body]);
      set("--r-size", `${pointsToCqi(style.sizes.body)}cqi`);
      set("--r-size-landscape", `${pointsToCqi(style.sizes.body, 297)}cqi`);
      set("--r-title", `${style.sizes.title / style.sizes.body}em`);
      set("--m-top", String(l.margins.top));
      set("--m-bottom", String(l.margins.bottom));
      set("--m-left", String(l.margins.left));
      set("--m-right", String(l.margins.right));
    };
    apply(current);
    return { update: apply };
  }

  // An element of a page design: where it sits, in shares of the page, and how it's drawn.
  function place(node: HTMLElement, e: Element) {
    const apply = (el: Element) => {
      const set = (name: string, value: string) => node.style.setProperty(name, value);
      set("left", `${(el.x / 210) * 100}%`);
      set("top", `${(el.y / 297) * 100}%`);
      set("width", `${(el.w / 210) * 100}%`);
      set("height", `${(el.h / 297) * 100}%`);
      set("font-family", FONT_STACKS[el.font === "heading" ? look.style.fonts.heading : el.font === "mono" ? "plex-mono" : look.style.fonts.body]);
      set("font-size", `${pointsToCqi(el.size)}cqi`);
      set("font-weight", el.weight === "bold" ? "600" : "400");
      set("color", colourOf(look.style, el.colour));
      set("text-align", el.align);
      set("justify-content", { left: "flex-start", center: "center", right: "flex-end" }[el.align]);
      if (el.kind === "box") {
        set("background", el.fill ? colourOf(look.style, el.fill) : "transparent");
        set("border", el.stroke && el.stroke_width ? `${(el.stroke_width / 210) * 100}cqi solid ${colourOf(look.style, el.stroke)}` : "none");
        set("border-radius", `${(el.radius / 210) * 100}cqi`);
      }
    };
    apply(e);
    return { update: apply };
  }

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
        {@const name = signer.role === "company" ? company : SAMPLE_SIGNERS[signer.role]}
        <figure class="signature">
          {#if signer.style === "stamp"}
            <div class="stamp">
              {#if look.logos.company}<img src={look.logos.company} alt="" />{/if}
              <span><strong>{name}</strong>{language === "da" ? "Digitalt underskrevet" : "Digitally signed"}</span>
            </div>
          {:else}
            <div class="hand"><span>{name}</span></div>
          {/if}
          <figcaption><strong>{signer.label}</strong>{name}{b.showDate ? ` · ${language === "da" ? "underskrevet" : "signed"} ${signedOn}` : ""}</figcaption>
        </figure>
      {/each}
    </div>
    <p class="sample-note">Sample signatures. In the PDF each one is a digital signature that can be checked.</p>
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

{#snippet design(page: PageName, index: number, logos: boolean)}
  <div class="design" aria-hidden="true">
    <!-- Lines are drawn on the page in millimetres, so their widths are exact. -->
    <svg class="lines" viewBox="0 0 210 297" preserveAspectRatio="none">
      {#each look.style.pages[page].elements.filter((e) => e.kind === "line" && e.stroke) as e (e.id)}
        <line x1={e.x} y1={e.y} x2={e.x + e.w} y2={e.y + e.h} stroke={colourOf(look.style, e.stroke ?? "line")} stroke-width={e.stroke_width} />
      {/each}
    </svg>
    {#each look.style.pages[page].elements.filter((e) => e.kind !== "line" && (logos || e.kind !== "logo")) as e (e.id)}
      <div class="el kind-{e.kind}" use:place={e}>
        {#if e.kind === "logo"}
          {#if look.logos[e.logo]}<img src={look.logos[e.logo]} alt="" />{:else}<span class="logo-name">{e.logo === "company" ? company : "Customer logo"}</span>{/if}
        {:else if e.kind === "image"}
          {#if e.asset && look.image(e.asset)}<img src={look.image(e.asset)} alt="" />{/if}
        {:else if e.kind !== "box"}
          <span>{words(e, page, index)}</span>
        {/if}
      </div>
    {/each}
  </div>
{/snippet}

<div class="pages" class:choosing={!!onselect} aria-label="The PDF's pages, with the sample answers" use:choose use:dress={look}>
  {#each paged.pages as page, p (p)}
    <section class="sheet {page.orientation}" class:cover-sheet={page.cover} bind:this={sheets[p]} aria-label="Page {p + 1} of {total}">
      <div class="paper">
        {#if page.orientation === "portrait" && (p === 0 ? look.art.first : look.art.other)}
          <img class="art" src={p === 0 ? look.art.first : look.art.other} alt="" />
        {/if}
        {@render design(designOf(p), p, !page.items.some((placed) => placed.block.kind === "cover" && !placed.block.showLogo))}
        <div class="body">
          {#each page.items as placed, i (i)}{@render item(placed.block, placed)}{/each}
        </div>
        {#if look.madeWith}<p class="made-with">Made with Skjald</p>{/if}
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
  /* The report's own look (its style, or the Skjald default), whatever the app's theme. */
  .paper {
    --paper: #ffffff;
    --text-ink: var(--r-text, #0f1b2d);
    --text-soft: var(--r-muted, #5b6675);
    --rule: var(--r-line, #e5e5e5);
    --subtle: var(--r-head, #efefef);
    position: relative;
    container-type: inline-size;
    aspect-ratio: 210 / 297;
    overflow: hidden;
    border: 1px solid var(--border);
    background: var(--paper);
    color: var(--text-ink);
    font-family: var(--r-font-body, var(--font-sans));
  }
  .landscape .paper {
    aspect-ratio: 297 / 210;
  }
  .art,
  .design,
  .lines {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .art {
    object-fit: fill;
  }
  .el {
    position: absolute;
    display: flex;
    align-items: center;
    overflow: hidden;
    line-height: 1.2;
    white-space: nowrap;
  }
  .el img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .kind-logo,
  .kind-image {
    align-items: flex-start;
  }
  .logo-name {
    font-family: var(--r-font-heading, var(--font-display));
  }
  /* The margins, in millimetres, as shares of the page; the body reaches --room past
     them, padded back by as much, so a chosen block's outline isn't cut off where the
     text area ends (overflow is clipped at the padding's edge). */
  .body {
    --room: 0.6em;
    position: absolute;
    top: calc(var(--m-top, 22) / 297 * 100% - var(--room));
    bottom: calc(var(--m-bottom, 20) / 297 * 100% - var(--room));
    left: calc(var(--m-left, 18) / 210 * 100% - var(--room));
    right: calc(var(--m-right, 18) / 210 * 100% - var(--room));
    padding: var(--room);
    overflow: hidden;
    font-size: var(--r-size, 1.764cqi);
    line-height: 1.6;
  }
  .landscape .body {
    top: calc(var(--m-top, 22) / 210 * 100% - var(--room));
    bottom: calc(var(--m-bottom, 20) / 210 * 100% - var(--room));
    left: calc(var(--m-left, 18) / 297 * 100% - var(--room));
    right: calc(var(--m-right, 18) / 297 * 100% - var(--room));
    font-size: var(--r-size-landscape, 1.247cqi);
  }
  .made-with {
    position: absolute;
    bottom: 1.6%;
    left: 0;
    right: 0;
    margin: 0;
    color: var(--text-soft);
    font-size: 0.95cqi;
    text-align: center;
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
    color: var(--r-link, #2b5d8a);
  }
  h1,
  h2,
  h3,
  .body :global(h3),
  .body :global(h4) {
    margin: 0.8em 0 0.4em;
    color: var(--r-heading, #0f1b2d);
    font-family: var(--r-font-heading, var(--font-display));
    font-weight: 400;
    line-height: 1.2;
  }
  h1 {
    font-size: var(--r-title, 2.86em);
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
    color: var(--r-head-ink, #0f1b2d);
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
    background: var(--fill, var(--r-info-fill, #dce6ee));
    color: var(--ink, var(--r-info-ink, #234c72));
  }
  .callout :global(p:last-child) {
    margin-bottom: 0;
  }
  .tone-note {
    --fill: var(--r-note-fill, #efefef);
    --ink: var(--r-note-ink, #0f1b2d);
  }
  .tone-warning {
    --fill: var(--r-warning-fill, #fbefd9);
    --ink: var(--r-warning-ink, #8a5a12);
  }
  .tone-critical {
    --fill: var(--r-critical-fill, #f9e3e0);
    --ink: var(--r-critical-ink, #a3352a);
  }
  .tone-success {
    --fill: var(--r-success-fill, #e3f1e8);
    --ink: var(--r-success-ink, #2f6b47);
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
    font-family: var(--r-font-heading, var(--font-display));
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
    max-width: 50%;
  }
  .signature {
    display: grid;
    flex: 1;
    align-content: start;
    gap: 0.5em;
    min-width: 0;
    margin: 0;
  }
  .hand,
  .stamp {
    display: flex;
    align-items: center;
    height: 4em;
  }
  .hand {
    padding-left: 0.4em;
    overflow: hidden;
    border-bottom: 1px solid var(--text-ink);
    color: #1b2f55;
    font-family: "Mr Dafoe", cursive;
    white-space: nowrap;
  }
  .hand span {
    font-size: 2.2em;
  }
  /* The company seal: a double frame in the style's link colour, with the logo. */
  .stamp {
    gap: 0.7em;
    padding: 0 0.8em;
    overflow: hidden;
    border: 2px solid var(--r-link, #2b5d8a);
    border-radius: 0.4em;
    box-shadow: inset 0 0 0 2px var(--paper), inset 0 0 0 3px var(--r-link, #2b5d8a);
    color: var(--r-link, #2b5d8a);
    line-height: 1.25;
  }
  .stamp img {
    max-width: 2.4em;
    max-height: 2.4em;
    object-fit: contain;
  }
  .stamp span {
    display: grid;
    min-width: 0;
    font-size: 0.85em;
  }
  .stamp strong,
  .signature figcaption strong {
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .signature figcaption {
    display: grid;
    color: var(--text-soft);
    font-size: 0.85em;
  }
  .signature figcaption strong {
    color: var(--text-ink);
  }
  .sample-note {
    margin-top: 0.8em;
    color: var(--text-soft);
    font-size: 0.8em;
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
