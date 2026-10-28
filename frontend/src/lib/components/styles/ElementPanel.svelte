<script lang="ts">
  import Trash from "@lucide/svelte/icons/trash-2";
  import Upload from "@lucide/svelte/icons/upload";
  import { NAMED_COLOURS, type Element } from "#lib/reportStyles/resolve.js";

  // The chosen element's settings: where it is and how big, in millimetres, and what it
  // shows. Text can hold {{ expressions }} reading the report's context and the shared
  // library, such as {{ customer.name }}; the server checks them when the style is saved.
  let {
    element = $bindable(),
    images,
    readonly = false,
    onupload,
    onremove,
  }: {
    element: Element;
    images: { sha256: string; url: string | null }[];
    readonly?: boolean;
    onupload: (file: File) => Promise<string | null>;
    onremove: () => void;
  } = $props();

  const COLOUR_NAMES: Record<string, string> = {
    text: "Text",
    muted: "Muted text",
    heading: "Headings",
    accent: "Accent",
    link: "Links",
    line: "Lines",
    classification: "Classification label",
  };
  const textual = $derived(["text", "page_number", "classification", "report_number"].includes(element.kind));

  function named(ref: string | null): string {
    return ref === null ? "none" : ref.startsWith("#") ? "custom" : ref;
  }

  function pickRef(field: "colour" | "fill" | "stroke", choice: string) {
    if (choice === "none") element[field] = null as never;
    else if (choice === "custom") element[field] = (element[field]?.startsWith("#") ? element[field] : "#2B5D8A") as never;
    else element[field] = choice as never;
  }

  async function upload(event: Event & { currentTarget: HTMLInputElement }) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    const sha = await onupload(file);
    if (sha) element.asset = sha;
  }

  const num = (value: string, fallback: number) => (Number.isFinite(Number(value)) && value !== "" ? Number(value) : fallback);
</script>

{#snippet colourRef(field: "colour" | "fill" | "stroke", label: string, optional: boolean)}
  {@const value = element[field]}
  <div class="field">
    <label for="el-{field}">{label}</label>
    <div class="row">
      <select id="el-{field}" class="input" value={named(value)} disabled={readonly} onchange={(e) => pickRef(field, e.currentTarget.value)}>
        {#if optional}<option value="none">None</option>{/if}
        {#each NAMED_COLOURS as name (name)}<option value={name}>{COLOUR_NAMES[name]}</option>{/each}
        <option value="custom">Another colour</option>
      </select>
      {#if value?.startsWith("#")}
        <input type="color" class="swatch" aria-label="{label}: pick a colour" value={value.toLowerCase()} disabled={readonly}
          oninput={(e) => (element[field] = e.currentTarget.value.toUpperCase() as never)} />
      {/if}
    </div>
  </div>
{/snippet}

<div class="panel stack">
  <div class="grid">
    <div class="field"><label for="el-x">From the left (mm)</label>
      <input id="el-x" class="input" type="number" step="0.5" min="0" max="210" value={element.x} disabled={readonly}
        onchange={(e) => (element.x = Math.min(num(e.currentTarget.value, element.x), 210 - element.w))} /></div>
    <div class="field"><label for="el-y">From the top (mm)</label>
      <input id="el-y" class="input" type="number" step="0.5" min="0" max="297" value={element.y} disabled={readonly}
        onchange={(e) => (element.y = Math.min(num(e.currentTarget.value, element.y), 297 - element.h))} /></div>
    <div class="field"><label for="el-w">Width (mm)</label>
      <input id="el-w" class="input" type="number" step="0.5" min="0" max="210" value={element.w} disabled={readonly}
        onchange={(e) => (element.w = Math.min(num(e.currentTarget.value, element.w), 210 - element.x))} /></div>
    <div class="field"><label for="el-h">Height (mm)</label>
      <input id="el-h" class="input" type="number" step="0.5" min="0" max="297" value={element.h} disabled={readonly}
        onchange={(e) => (element.h = Math.min(num(e.currentTarget.value, element.h), 297 - element.y))} /></div>
  </div>

  {#if element.kind === "text"}
    <div class="field">
      <label for="el-text">Text</label>
      <input id="el-text" class="input" bind:value={element.text} maxlength="500" disabled={readonly} />
      <span class="hint">Variables go in {"{{ }}"}, such as {"{{ customer.name }}"}, {"{{ project.number }}"} or {"{{ vars.support_phone }}"}.</span>
    </div>
  {/if}

  {#if element.kind === "logo"}
    <div class="field">
      <label for="el-logo">Whose logo</label>
      <select id="el-logo" class="input" bind:value={element.logo} disabled={readonly}>
        <option value="company">The company's</option>
        <option value="customer">The customer's</option>
      </select>
      <span class="hint">The company's is set in Admin → Branding, a customer's on the customer. Without one, nothing prints.</span>
    </div>
  {/if}

  {#if element.kind === "image"}
    <div class="field">
      <label for="el-image">Picture</label>
      <select id="el-image" class="input" value={element.asset ?? ""} disabled={readonly} onchange={(e) => (element.asset = e.currentTarget.value || null)}>
        {#each images as img, i (img.sha256)}<option value={img.sha256}>Picture {i + 1}</option>{/each}
      </select>
      <label class="button button-secondary upload">
        <Upload size={16} aria-hidden="true" /> Upload a picture
        <input type="file" class="visually-hidden" accept="image/png,image/jpeg,image/svg+xml,.svg" disabled={readonly} onchange={upload} />
      </label>
      <span class="hint">PNG, JPEG or SVG, up to 4 MB. SVGs are cleaned of anything but drawing.</span>
    </div>
  {/if}

  {#if textual}
    <div class="grid">
      <div class="field"><label for="el-font">Font</label>
        <select id="el-font" class="input" bind:value={element.font} disabled={readonly}>
          <option value="body">Body</option><option value="heading">Headings</option><option value="mono">Mono</option>
        </select></div>
      <div class="field"><label for="el-size">Size (pt)</label>
        <input id="el-size" class="input" type="number" min="5" max="48" step="0.5" value={element.size} disabled={readonly}
          onchange={(e) => (element.size = Math.min(48, Math.max(5, num(e.currentTarget.value, element.size))))} /></div>
      <div class="field"><label for="el-weight">Weight</label>
        <select id="el-weight" class="input" bind:value={element.weight} disabled={readonly}>
          <option value="regular">Regular</option><option value="bold">Bold</option>
        </select></div>
      <div class="field"><label for="el-align">Align</label>
        <select id="el-align" class="input" bind:value={element.align} disabled={readonly}>
          <option value="left">Left</option><option value="center">Centre</option><option value="right">Right</option>
        </select></div>
    </div>
    {@render colourRef("colour", "Colour", false)}
  {/if}

  {#if element.kind === "box"}
    {@render colourRef("fill", "Fill", true)}
  {/if}
  {#if element.kind === "box" || element.kind === "line"}
    {@render colourRef("stroke", element.kind === "line" ? "Colour" : "Outline", true)}
    <div class="grid">
      <div class="field"><label for="el-stroke">{element.kind === "line" ? "Thickness" : "Outline thickness"} (mm)</label>
        <input id="el-stroke" class="input" type="number" min="0" max="5" step="0.1" value={element.stroke_width} disabled={readonly}
          onchange={(e) => (element.stroke_width = Math.min(5, Math.max(0, num(e.currentTarget.value, element.stroke_width))))} /></div>
      {#if element.kind === "box"}
        <div class="field"><label for="el-radius">Corner radius (mm)</label>
          <input id="el-radius" class="input" type="number" min="0" max="20" step="0.5" value={element.radius} disabled={readonly}
            onchange={(e) => (element.radius = Math.min(20, Math.max(0, num(e.currentTarget.value, element.radius))))} /></div>
      {/if}
    </div>
  {/if}

  {#if !readonly}
    <button class="button button-secondary danger" type="button" onclick={onremove}><Trash size={16} aria-hidden="true" /> Remove this element</button>
  {/if}
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
  }
  .row {
    display: flex;
    gap: var(--space-2);
  }
  .swatch {
    width: 2.5rem;
    min-width: 2.5rem;
    padding: 2px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
  }
  .upload {
    align-self: flex-start;
    margin-top: var(--space-2);
  }
  .danger {
    align-self: flex-start;
    color: var(--critical-text);
  }
</style>
