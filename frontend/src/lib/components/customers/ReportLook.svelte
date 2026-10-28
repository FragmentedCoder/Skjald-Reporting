<script lang="ts">
  import { resolve } from "$app/paths";
  import Trash from "@lucide/svelte/icons/trash-2";
  import Upload from "@lucide/svelte/icons/upload";
  import { onMount } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { dateTime } from "#lib/format.js";
  import { backgroundApi, stylesApi, whenConverted, type Background, type CustomerStyles } from "#lib/reportStyles/api.js";
  import type { Margins } from "#lib/reportStyles/resolve.js";
  import { toast } from "#lib/toast.svelte.js";

  // How a customer's reports look: the background they print on (the customer's
  // letterhead, usually an A4 PDF) and the styles technicians may choose among.
  let { customerId, customerName }: { customerId: number; customerName: string } = $props();

  // The report background
  let background = $state<Background | null>(null);
  let loaded = $state(false);
  let working = $state(false);
  let margins = $state<Margins>({ top: 30, bottom: 25, left: 20, right: 20 });

  async function loadBackground() {
    try {
      background = await backgroundApi.get(customerId);
      margins = { ...background.margins };
    } catch (e) {
      background = null;
      if (!(e instanceof ApiError && e.status === 404) && !sessionGone(e)) toast(e instanceof ApiError ? e.message : "The report background couldn't be loaded.", "critical");
    } finally {
      loaded = true;
    }
  }

  async function upload(event: Event & { currentTarget: HTMLInputElement }) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    working = true;
    try {
      background = await backgroundApi.upload(customerId, file);
      if (background.status === "converting") background = await whenConverted(() => backgroundApi.get(customerId));
      margins = { ...background.margins };
      if (background.status === "ready") toast("Report background saved.", "ok");
      else if (background.status === "failed") toast(background.message || "The file couldn't be converted.", "critical");
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The report background couldn't be saved.", "critical");
    } finally {
      working = false;
    }
  }

  async function saveMargins(event: SubmitEvent) {
    event.preventDefault();
    try {
      background = await backgroundApi.margins(customerId, margins);
      toast("Margins saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The margins couldn't be saved.", "critical");
    }
  }

  async function remove() {
    try {
      await backgroundApi.remove(customerId);
      background = null;
      toast("Report background removed: reports print on plain pages.", "ok");
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The report background couldn't be removed.", "critical");
    }
  }

  function guides(node: HTMLElement, m: Margins) {
    const apply = (v: Margins) => {
      node.style.setProperty("top", `${(v.top / 297) * 100}%`);
      node.style.setProperty("bottom", `${(v.bottom / 297) * 100}%`);
      node.style.setProperty("left", `${(v.left / 210) * 100}%`);
      node.style.setProperty("right", `${(v.right / 210) * 100}%`);
    };
    apply(m);
    return { update: apply };
  }

  const MARGINS: { key: keyof Margins; label: string; most: number }[] = [
    { key: "top", label: "Top", most: 80 },
    { key: "bottom", label: "Bottom", most: 80 },
    { key: "left", label: "Left", most: 60 },
    { key: "right", label: "Right", most: 60 },
  ];

  // The styles
  let styles = $state<CustomerStyles | null>(null);
  let chosenDefault = $state("");
  let allowed = $state<number[]>([]);

  async function loadStyles() {
    try {
      styles = await stylesApi.customerStyles(customerId);
      chosenDefault = styles.default_style_id === null ? "" : String(styles.default_style_id);
      allowed = [...styles.allowed];
    } catch (e) {
      if (!sessionGone(e)) styles = null;
    }
  }

  async function saveStyles(event: SubmitEvent) {
    event.preventDefault();
    try {
      styles = await stylesApi.setCustomerStyles(customerId, chosenDefault ? Number(chosenDefault) : null, allowed);
      allowed = [...styles.allowed];
      toast("Report styles saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The report styles couldn't be saved.", "critical");
    }
  }

  function toggle(id: number, on: boolean) {
    allowed = on ? [...allowed, id] : allowed.filter((a) => a !== id);
  }

  const others = $derived((styles?.choices ?? []).filter((s) => String(s.id) !== chosenDefault));
  const companyDefault = $derived(styles?.choices.find((s) => s.id === styles?.company_default)?.name ?? "the Skjald default");
  onMount(() => void Promise.all([loadBackground(), loadStyles()]));
</script>

<section class="section" aria-labelledby="background-title">
  <h2 class="section-title" id="background-title">Report background</h2>
  <p class="small muted">
    The art {customerName}'s reports print on, such as their letterhead: an A4 PDF (save a Word file as PDF first), or a
    PNG, JPEG or SVG picture of an A4 page, up to 10 MB. A PDF's first page goes behind a report's first page and its
    second, if it has one, behind the rest. Without one, reports print on plain pages. Each template can choose not to
    use it.
  </p>
  {#if !loaded}
    <p class="muted small">Loading…</p>
  {:else if background}
    {#if background.status === "converting" || working}
      <p class="alert alert-info small" role="status">Converting the PDF… this takes a few seconds.</p>
    {:else if background.status === "failed"}
      <p class="alert alert-critical small" role="alert">{background.message || "The file couldn't be converted."} Upload another.</p>
    {:else}
      <div class="pages">
        {#each Array.from({ length: background.pages }, (_, i) => i + 1) as n (n)}
          <figure>
            <div class="sheet">
              <img src={backgroundApi.pageUrl(customerId, n, background.uploaded_at)} alt="Page {n} of the report background" />
              <div class="margins" use:guides={margins} aria-hidden="true"></div>
            </div>
            <figcaption class="small muted">{background.pages === 1 ? "Behind every page" : n === 1 ? "Behind the first page" : "Behind the rest"}</figcaption>
          </figure>
        {/each}
      </div>
      <form class="stack" onsubmit={saveMargins}>
        <p class="small muted">Margins keep the report's text clear of the art (the dashed box), in millimetres.</p>
        <div class="grid">
          {#each MARGINS as m (m.key)}
            <div class="field">
              <label for="bg-margin-{m.key}">{m.label}</label>
              <input id="bg-margin-{m.key}" class="input" type="number" min="5" max={m.most} step="1" bind:value={margins[m.key]} required />
            </div>
          {/each}
        </div>
        <div><button class="button button-secondary" type="submit">Save margins</button></div>
      </form>
    {/if}
    <p class="small muted">Uploaded by {background.uploaded_by ?? "someone"}, {dateTime(background.uploaded_at)}.</p>
  {:else}
    <p class="small">No report background: reports print on plain pages, or the style's own artwork.</p>
  {/if}
  <div class="button-row">
    <label class="button button-secondary" class:disabled={working}>
      <Upload size={16} aria-hidden="true" /> {background ? "Replace the background" : "Upload a background"}
      <input type="file" class="visually-hidden" accept="application/pdf,.pdf,image/png,image/jpeg,image/svg+xml,.svg" disabled={working} onchange={upload} />
    </label>
    {#if background}
      <button class="button button-secondary" type="button" disabled={working} onclick={remove}><Trash size={16} aria-hidden="true" /> Remove</button>
    {/if}
  </div>
</section>

{#if styles}
  <section class="section" aria-labelledby="styles-title">
    <h2 class="section-title" id="styles-title">Report style</h2>
    <p class="small muted">Which style {customerName}'s reports start in, and which others a technician may choose. Styles are made under <a href={resolve("/(app)/styles")}>Styles</a>.</p>
    <form class="stack form-narrow" onsubmit={saveStyles}>
      <div class="field">
        <label for="default-style">Reports start in</label>
        <select id="default-style" class="input" bind:value={chosenDefault}>
          <option value="">The company default ({companyDefault})</option>
          {#each styles.choices as s (s.id)}<option value={String(s.id)}>{s.name}{s.customer_id ? ` (${customerName}'s own)` : ""}</option>{/each}
        </select>
      </div>
      {#if others.length}
        <fieldset class="field">
          <legend>Technicians may also choose</legend>
          {#each others as s (s.id)}
            <label class="check"><input type="checkbox" checked={allowed.includes(s.id)} onchange={(e) => toggle(s.id, e.currentTarget.checked)} /> {s.name}</label>
          {/each}
        </fieldset>
      {/if}
      <div><button class="button button-primary" type="submit">Save report styles</button></div>
    </form>
  </section>
{/if}

<style>
  .pages {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }
  figure {
    margin: 0;
    width: 11rem;
  }
  .sheet {
    position: relative;
    aspect-ratio: 210 / 297;
    border: 1px solid var(--border);
    background: #ffffff;
  }
  .sheet img {
    width: 100%;
    height: 100%;
    object-fit: fill;
  }
  .margins {
    position: absolute;
    border: 1px dashed rgb(163 53 42 / 0.7);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 6rem));
    gap: var(--space-3);
  }
  .form-narrow {
    max-width: 480px;
  }
  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-2);
    font-weight: 500;
  }
  .check {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .disabled {
    opacity: 0.6;
    pointer-events: none;
  }
</style>
