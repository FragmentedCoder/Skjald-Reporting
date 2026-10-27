<script lang="ts">
  import { beforeNavigate } from "$app/navigation";
  import { resolve as route } from "$app/paths";
  import { page as current } from "$app/state";
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Upload from "@lucide/svelte/icons/upload";
  import { onDestroy, onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { branding, pageTitle } from "#lib/branding.svelte.js";
  import PdfPages from "#lib/components/preview/PdfPages.svelte";
  import ColourField from "#lib/components/styles/ColourField.svelte";
  import ElementPanel from "#lib/components/styles/ElementPanel.svelte";
  import PageDesigner from "#lib/components/styles/PageDesigner.svelte";
  import type { CustomerDetail } from "#lib/customers.js";
  import { dateTime } from "#lib/format.js";
  import { backgroundApi, stylesApi, whenConverted, type Style, type StyleSummary } from "#lib/reportStyles/api.js";
  import { lookOf, pageTexts, type CustomerArt } from "#lib/reportStyles/look.js";
  import { imageOf } from "#lib/reportStyles/preview.svelte.js";
  import {
    COLOUR_KEYS,
    COLOUR_LABELS,
    contrastProblems,
    element as newElement,
    emptyContent,
    NEEDED,
    PAGE_NAMES,
    resolve,
    TONE_LABELS,
    TONE_NAMES,
    type Element,
    type ElementKind,
    type Font,
    type Margins,
    type PageDesign,
    type PageName,
    type StyleContent,
  } from "#lib/reportStyles/resolve.js";
  import { sampleTemplate } from "#lib/shared.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { sampleContext } from "#lib/templates/preview.js";
  import type { TemplateContent } from "#lib/templates/types.js";
  import { toast } from "#lib/toast.svelte.js";

  // One style: its colours and type, margins, page designs and artwork, beside the sample
  // incident report drawn in it. A style keeps only what it changes from the one below
  // (the Skjald default, or for a customer's style one of the company's); each value
  // says whether it's set here. Saving makes a new version.
  const id = $derived(Number(current.params.id));
  let style = $state<Style | null>(null);
  let error = $state<string | null>(null);
  let name = $state("");
  let basedOn = $state<number | null>(null);
  let content = $state<StyleContent>(emptyContent());
  let below = $state<StyleContent[]>([]);
  let saved = $state("");
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let companyStyles = $state<StyleSummary[]>([]);
  let customerLogo = $state<string | null>(null);
  let customerArt = $state<CustomerArt | null>(null);
  let showBackground = $state(true);

  const snapshotOf = () => JSON.stringify({ name, basedOn, content: $state.snapshot(content) });
  const changed = $derived(style !== null && JSON.stringify({ name, basedOn, content }) !== saved);
  const lower = $derived(resolve(below));
  const resolved = $derived(resolve([...below, content]));
  const weak = $derived(contrastProblems(resolved));
  const image = $derived(imageOf(style));
  const logos = $derived({ company: branding.current.logo_url, customer: customerLogo });

  function use(found: Style) {
    style = found;
    name = found.name;
    basedOn = found.based_on;
    content = found.content;
    below = found.below;
    saved = snapshotOf();
  }

  async function load() {
    try {
      use(await stylesApi.get(id));
      error = null;
      companyStyles = (await stylesApi.list()).filter((s) => s.customer_id === null);
      if (style?.customer_id) await loadCustomer(style.customer_id);
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The style could not be loaded.";
    }
  }
  onMount(load);

  async function loadCustomer(customerId: number) {
    try {
      customerLogo = (await api<CustomerDetail>("GET", `/customers/${customerId}`)).logo_url;
    } catch {
      customerLogo = null;
    }
    try {
      const found = await backgroundApi.get(customerId);
      if (found.status === "ready" && found.pages) {
        const pages = Array.from({ length: found.pages }, (_, i) => backgroundApi.pageUrl(customerId, i + 1, found.uploaded_at));
        customerArt = { pages, margins: found.margins };
      }
    } catch {
      customerArt = null;
    }
  }

  // Choosing another company style to stack on shows its look at once.
  async function stackOn(value: string) {
    basedOn = value ? Number(value) : null;
    below = basedOn === null ? [] : [(await stylesApi.get(basedOn)).content];
  }

  async function save() {
    if (!style) return;
    saving = true;
    saveError = null;
    try {
      use(await stylesApi.update(style.id, { name, based_on: basedOn, content: $state.snapshot(content) as StyleContent, version: style.version }));
      toast("Style saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) saveError = e instanceof ApiError ? e.message : "The style couldn't be saved.";
    } finally {
      saving = false;
    }
  }

  beforeNavigate(({ cancel, willUnload }) => {
    if (changed && !willUnload && !confirm("This style has changes that aren't saved. Leave without saving them?")) cancel();
  });

  // Colours, tones, fonts, sizes and margins

  function setTone(tone: (typeof TONE_NAMES)[number], part: "fill" | "ink", value: string | null) {
    if (value === null) {
      content.tones[tone] = null;
      return;
    }
    const now = content.tones[tone] ?? { ...resolved.tones[tone] };
    content.tones[tone] = { ...now, [part]: value };
  }

  const FONTS: { value: Font; label: string }[] = [
    { value: "marcellus", label: "Marcellus" },
    { value: "plex-sans", label: "IBM Plex Sans" },
    { value: "plex-mono", label: "IBM Plex Mono" },
  ];
  const MARGINS: { key: keyof Margins; label: string; most: number }[] = [
    { key: "top", label: "Top", most: 80 },
    { key: "bottom", label: "Bottom", most: 80 },
    { key: "left", label: "Left", most: 60 },
    { key: "right", label: "Right", most: 60 },
  ];

  function setNumber<K extends string>(group: Partial<Record<K, number | null>>, key: K, raw: string, low: number, high: number) {
    const value = Number(raw);
    group[key] = raw === "" || !Number.isFinite(value) ? null : Math.min(high, Math.max(low, value));
  }

  // Page designs

  let tab = $state<"look" | "pages" | "artwork">("look");
  let pageName = $state<PageName>("first");
  let selected = $state<string | null>(null);
  const PAGE_LABELS: Record<PageName, string> = { cover: "Cover", first: "First page", other: "Other pages" };
  const own = $derived(content.pages[pageName] ?? null);
  const chosen = $derived(own?.elements.find((e) => e.id === selected) ?? null);

  function designHere() {
    content.pages[pageName] = structuredClone($state.snapshot(lower.pages[pageName])) as PageDesign;
  }

  const ADDABLE: { kind: ElementKind; label: string; make: () => Partial<Element> }[] = [
    { kind: "text", label: "Text", make: () => ({ w: 80, h: 6, text: "{{ customer.name }}" }) },
    { kind: "logo", label: "Logo", make: () => ({ w: 36, h: 10 }) },
    { kind: "image", label: "Image", make: () => ({ w: 30, h: 20 }) },
    { kind: "line", label: "Line", make: () => ({ w: 174, h: 0 }) },
    { kind: "box", label: "Box", make: () => ({ w: 60, h: 12, fill: "accent", stroke: null }) },
    { kind: "page_number", label: "Page number", make: () => ({ w: 40, h: 5, size: 8, colour: "muted" }) },
    { kind: "classification", label: "Classification", make: () => ({ w: 40, h: 5, size: 8, colour: "classification", weight: "bold" }) },
    { kind: "report_number", label: "Report number", make: () => ({ w: 50, h: 5, size: 8, colour: "muted" }) },
  ];

  function add(kind: ElementKind) {
    const design = content.pages[pageName];
    if (!design) return;
    const extra = ADDABLE.find((a) => a.kind === kind)?.make() ?? {};
    if (kind === "image") {
      const first = style?.assets.find((a) => a.content_type !== "image/svg+xml" || a.width < 600);
      if (!first) {
        toast("Upload a picture first: choose Image again once it's there.", "warning");
        tab = "pages";
        pickImage();
        return;
      }
      extra.asset = first.sha256;
    }
    const made = newElement({ id: `e_${Math.random().toString(36).slice(2, 10).padEnd(6, "0")}`, kind, x: resolved.margins.left, y: 8, w: 40, h: 6, ...extra } as Element);
    made.w = Math.min(made.w, 210 - made.x);
    design.elements.push(made);
    selected = made.id;
  }

  function removeChosen() {
    const design = content.pages[pageName];
    if (!design || !selected) return;
    design.elements = design.elements.filter((e) => e.id !== selected);
    selected = null;
  }

  // Pictures

  let imageInput = $state<HTMLInputElement>();
  function pickImage() {
    imageInput?.click();
  }

  async function uploadImage(file: File): Promise<string | null> {
    if (!style) return null;
    try {
      const done = await stylesApi.upload(style.id, file, "image");
      style.assets = (await stylesApi.get(style.id)).assets;
      return done.pages[0] ?? null;
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The picture couldn't be added.", "critical");
      return null;
    }
  }

  async function imagePicked(event: Event & { currentTarget: HTMLInputElement }) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (file && (await uploadImage(file))) toast("Picture added: choose Image to place it.", "ok");
  }

  let converting = $state(false);
  async function uploadArtwork(event: Event & { currentTarget: HTMLInputElement }) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !style) return;
    const styleId = style.id;
    converting = true;
    try {
      let done = await stylesApi.upload(styleId, file, "artwork");
      if (done.status === "converting" && done.upload) done = await whenConverted(() => stylesApi.uploadStatus(styleId, done.upload as number));
      if (done.status === "ready") {
        style.assets = (await stylesApi.get(styleId)).assets;
        content.artwork = { first: done.pages[0], other: done.pages[1] ?? done.pages[0] };
        toast(done.pages.length > 1 ? "Artwork added: its first page goes behind a report's first page, its second behind the rest." : "Artwork added: it goes behind every page.", "ok");
      } else if (done.status === "failed") {
        toast(done.message || "The artwork couldn't be converted.", "critical");
      } else {
        toast("The artwork is still being converted. Try again in a minute.", "warning");
      }
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The artwork couldn't be added.", "critical");
    } finally {
      converting = false;
    }
  }

  // The sample report, drawn in the style.
  const live = new LivePreview();
  onDestroy(() => live.close());
  $effect(() => {
    const sample = sampleTemplate as unknown as TemplateContent;
    live.update({ content: sample, answers: sample.sample.answers, context: sampleContext(), assets: {}, timezone: branding.current.time_zone,
      pageTexts: pageTexts(resolved) });
  });
  const look = $derived(lookOf(resolved, { image, customerArt: showBackground ? customerArt : null, logos, madeWith: branding.current.made_with_skjald, texts: live.model?.pageTexts }));
  const art = $derived(pageName === "other" ? look.art.other : look.art.first);
</script>

<svelte:head><title>{pageTitle(style ? style.name : "Style")}</title></svelte:head>

<main class="page-content">
  <a class="back small" href={route("/(app)/styles")}><ArrowLeft size={16} aria-hidden="true" /> Styles</a>
  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if style}
    <div class="page-header">
      <div>
        <h1 class="title">{style.name}</h1>
        <p class="small muted">
          {style.customer_id ? `${style.customer_name}'s style, sealed with the customer's key` : "A company style"} ·
          version {style.version}, saved by {style.updated_by ?? "someone"}, {dateTime(style.updated_at)}
        </p>
      </div>
      <button class="button button-primary" type="button" disabled={!changed || saving} onclick={save}>{changed ? "Save" : "Saved"}</button>
    </div>
    {#if saveError}<p class="alert alert-critical" role="alert">{saveError}</p>{/if}

    <div class="editor">
      <section class="settings" aria-label="The style's settings">
        <div class="stack">
          <div class="field">
            <label for="style-name">Name</label>
            <input id="style-name" class="input" bind:value={name} maxlength="100" required />
          </div>
          {#if style.customer_id}
            <div class="field">
              <label for="style-base">Stacks on</label>
              <select id="style-base" class="input" value={basedOn === null ? "" : String(basedOn)} onchange={(e) => void stackOn(e.currentTarget.value)}>
                <option value="">The Skjald default</option>
                {#each companyStyles as s (s.id)}<option value={String(s.id)}>{s.name}</option>{/each}
              </select>
            </div>
          {/if}
        </div>

        <nav class="tabs" aria-label="Settings">
          <button type="button" aria-pressed={tab === "look"} onclick={() => (tab = "look")}>Colours and type</button>
          <button type="button" aria-pressed={tab === "pages"} onclick={() => (tab = "pages")}>Page designs</button>
          <button type="button" aria-pressed={tab === "artwork"} onclick={() => (tab = "artwork")}>Artwork</button>
        </nav>

        {#if tab === "look"}
          <div class="stack">
            {#if weak.length}
              <div class="alert alert-warning small" role="status">
                <p>Some text won't read well: WCAG AA asks for {NEEDED}:1.</p>
                <ul>{#each weak as w (w.what)}<li>{w.what}: {w.ratio.toFixed(1)}:1</li>{/each}</ul>
              </div>
            {/if}
            <h2 class="section-title">Colours</h2>
            {#each COLOUR_KEYS as key (key)}
              <ColourField id="colour-{key}" label={COLOUR_LABELS[key]} value={content.colours[key]} inherited={lower.colours[key]}
                onchange={(v) => (content.colours[key] = v)} />
            {/each}

            <h2 class="section-title">Callout tones</h2>
            {#each TONE_NAMES as tone (tone)}
              <fieldset class="tone">
                <legend>{TONE_LABELS[tone]}</legend>
                <ColourField id="tone-{tone}-fill" label="Fill" value={content.tones[tone]?.fill} inherited={lower.tones[tone].fill} onchange={(v) => setTone(tone, "fill", v)} />
                <ColourField id="tone-{tone}-ink" label="Text" value={content.tones[tone]?.ink} inherited={lower.tones[tone].ink} onchange={(v) => setTone(tone, "ink", v)} />
              </fieldset>
            {/each}

            <h2 class="section-title">Type</h2>
            <div class="grid">
              <div class="field">
                <label for="font-heading">Headings</label>
                <select id="font-heading" class="input" value={content.fonts.heading ?? ""} onchange={(e) => (content.fonts.heading = (e.currentTarget.value || null) as Font | null)}>
                  <option value="">{FONTS.find((f) => f.value === lower.fonts.heading)?.label}, from the one below</option>
                  {#each FONTS as f (f.value)}<option value={f.value}>{f.label}</option>{/each}
                </select>
              </div>
              <div class="field">
                <label for="font-body">Body text</label>
                <select id="font-body" class="input" value={content.fonts.body ?? ""} onchange={(e) => (content.fonts.body = (e.currentTarget.value || null) as Font | null)}>
                  <option value="">{FONTS.find((f) => f.value === lower.fonts.body)?.label}, from the one below</option>
                  {#each FONTS as f (f.value)}<option value={f.value}>{f.label}</option>{/each}
                </select>
              </div>
              <div class="field">
                <label for="size-body">Body size (pt)</label>
                <input id="size-body" class="input" type="number" min="8" max="14" step="0.5" placeholder={String(lower.sizes.body)}
                  value={content.sizes.body ?? ""} onchange={(e) => setNumber(content.sizes, "body", e.currentTarget.value, 8, 14)} />
              </div>
              <div class="field">
                <label for="size-title">Cover title size (pt)</label>
                <input id="size-title" class="input" type="number" min="16" max="48" step="1" placeholder={String(lower.sizes.title)}
                  value={content.sizes.title ?? ""} onchange={(e) => setNumber(content.sizes, "title", e.currentTarget.value, 16, 48)} />
              </div>
            </div>
            <p class="hint">Fonts are bundled with Skjald and embedded in every PDF. A blank box keeps the value from the one below.</p>

            <h2 class="section-title">Margins (mm)</h2>
            <div class="grid">
              {#each MARGINS as m (m.key)}
                <div class="field">
                  <label for="margin-{m.key}">{m.label}</label>
                  <input id="margin-{m.key}" class="input" type="number" min="5" max={m.most} step="1" placeholder={String(lower.margins[m.key])}
                    value={content.margins[m.key] ?? ""} onchange={(e) => setNumber(content.margins, m.key, e.currentTarget.value, 5, m.most)} />
                </div>
              {/each}
            </div>
            <p class="hint">Where the report's text goes. A customer's report background brings margins of its own.</p>
          </div>
        {:else if tab === "pages"}
          <div class="stack">
            <div class="kinds" role="group" aria-label="Page">
              {#each PAGE_NAMES as p (p)}
                <button type="button" aria-pressed={pageName === p} onclick={() => { pageName = p; selected = null; }}>{PAGE_LABELS[p]}</button>
              {/each}
            </div>
            <p class="small muted">
              {pageName === "cover" ? "The cover, when a template has one." : pageName === "first" ? "The first page of the report after any cover." : "Every page after the first."}
              Place logos, text, lines and boxes around the text; the dashed box is where the text goes.
            </p>
            {#if own}
              <div class="add" role="group" aria-label="Add an element">
                {#each ADDABLE as a (a.kind)}<button class="button button-secondary small" type="button" onclick={() => add(a.kind)}>{a.label}</button>{/each}
              </div>
              {#if chosen}
                <h2 class="section-title">The chosen element</h2>
                {#key chosen.id}
                  <ElementPanel
                    bind:element={() => chosen as Element, (v) => Object.assign(chosen as Element, v)}
                    images={(style?.assets ?? []).filter((a) => !(a.content_type === "image/svg+xml" && a.width >= 500 && a.height / a.width > 1.3)).map((a) => ({ sha256: a.sha256, url: image(a.sha256) }))}
                    onupload={uploadImage}
                    onremove={removeChosen} />
                {/key}
              {:else}
                <p class="hint">Choose an element on the page to change it. Drag it to move it, or its corner to resize it; with the keyboard, the arrow keys move it.</p>
              {/if}
              <button class="link-button small" type="button" onclick={() => { content.pages[pageName] = null; selected = null; }}>Use the design from the one below</button>
            {:else}
              <p class="alert alert-info small">This page uses the design from the one below.</p>
              <button class="button button-secondary" type="button" onclick={designHere}>Design this page here</button>
            {/if}
            <input bind:this={imageInput} type="file" class="visually-hidden" accept="image/png,image/jpeg,image/svg+xml,.svg" onchange={imagePicked} />
          </div>
        {:else}
          <div class="stack">
            <p class="small muted">Finished artwork, drawn behind the pages: an A4 PDF, such as a letterhead saved from Word, or a PNG, JPEG or SVG picture of a page. A PDF's first page goes behind a report's first page and its second, if it has one, behind the rest.</p>
            {#if content.artwork === null}
              <p class="alert alert-info small">{lower.artwork.first ? "This style uses the artwork from the one below." : "No artwork: the pages are plain."}</p>
            {:else if !content.artwork.first && !content.artwork.other}
              <p class="alert alert-info small">Plain pages, whatever the one below has.</p>
            {:else}
              <div class="art-pages">
                {#each [["First page", content.artwork.first], ["Other pages", content.artwork.other]] as [label, sha] (label)}
                  <figure>
                    {#if sha && image(sha)}<img src={image(sha)} alt="Artwork for the {String(label).toLowerCase()}" />{:else}<div class="plain">Plain</div>{/if}
                    <figcaption class="small muted">{label}</figcaption>
                  </figure>
                {/each}
              </div>
            {/if}
            <div class="row">
              <label class="button button-secondary" class:disabled={converting}>
                <Upload size={16} aria-hidden="true" /> {converting ? "Converting…" : "Upload artwork"}
                <input type="file" class="visually-hidden" accept="application/pdf,.pdf,image/png,image/jpeg,image/svg+xml,.svg" disabled={converting} onchange={uploadArtwork} />
              </label>
              <button class="button button-secondary" type="button" onclick={() => (content.artwork = { first: null, other: null })}>Plain pages</button>
              {#if content.artwork !== null}
                <button class="link-button small" type="button" onclick={() => (content.artwork = null)}>Use the one below</button>
              {/if}
            </div>
            <p class="hint">Word files: save as PDF first. Up to 10 MB. PDFs are converted on the server with no network access, and drawings come out as clean vector graphics.</p>
          </div>
        {/if}
      </section>

      <section class="canvas" class:sticky={tab === "pages"} aria-label={tab === "pages" ? `The ${PAGE_LABELS[pageName].toLowerCase()}'s design` : "The sample report in this style"}>
        {#if customerArt}
          <label class="check small"><input type="checkbox" bind:checked={showBackground} /> Show with {style.customer_name}'s report background</label>
        {/if}
        {#if tab === "pages"}
          {#if own}
            <PageDesigner bind:design={() => own as PageDesign, (v) => (content.pages[pageName] = v)} style={resolved} margins={look.margins} {art} {image} {logos}
              company={branding.current.company_name ?? "Your company"} bind:selected />
          {:else}
            <PageDesigner design={lower.pages[pageName]} style={resolved} margins={look.margins} {art} {image} {logos}
              company={branding.current.company_name ?? "Your company"} readonly />
          {/if}
        {:else if live.paged}
          <PdfPages paged={live.paged} {look} company={branding.current.company_name ?? "Your company"} />
        {:else}
          <p class="muted">Drawing the sample report…</p>
        {/if}
      </section>
    </div>
  {:else if !error}
    <p class="muted">Loading…</p>
  {/if}
</main>

<style>
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    margin-bottom: var(--space-3);
  }
  .editor {
    display: grid;
    grid-template-columns: minmax(20rem, 28rem) minmax(0, 1fr);
    gap: var(--space-6);
    align-items: start;
  }
  @media (max-width: 960px) {
    .editor {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  /* The page being designed stays in view; the sample report scrolls with the page. */
  .sticky {
    position: sticky;
    top: var(--space-4);
  }
  .settings {
    display: grid;
    gap: var(--space-4);
  }
  .canvas {
    display: grid;
    gap: var(--space-3);
    justify-items: center;
  }
  .tabs,
  .kinds {
    display: inline-flex;
    flex-wrap: wrap;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .tabs button,
  .kinds button {
    padding: 4px 12px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--text-muted);
    font: inherit;
    cursor: pointer;
  }
  .tabs button[aria-pressed="true"],
  .kinds button[aria-pressed="true"] {
    background: var(--surface-subtle);
    color: var(--text);
    font-weight: 600;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
  }
  .tone {
    display: grid;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }
  .tone legend {
    padding: 0 var(--space-1);
    font-weight: 600;
  }
  .add,
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .art-pages {
    display: flex;
    gap: var(--space-3);
  }
  .art-pages figure {
    margin: 0;
    width: 8rem;
  }
  .art-pages img,
  .plain {
    display: grid;
    place-items: center;
    width: 100%;
    aspect-ratio: 210 / 297;
    border: 1px solid var(--border);
    background: #ffffff;
    color: var(--text-muted);
    object-fit: fill;
  }
  .check {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-self: start;
  }
  .disabled {
    opacity: 0.6;
    pointer-events: none;
  }
</style>
