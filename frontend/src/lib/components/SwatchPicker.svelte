<script lang="ts">
  import type { Swatch } from "$lib/colours";

  // Pick one colour from a short, contrast-checked list. With `siteName`, a first
  // option follows the site's colour (bound as "").
  let {
    legend,
    hint,
    swatches,
    value = $bindable(""),
    siteName,
    disabled = false,
  }: {
    legend: string;
    hint?: string;
    swatches: Swatch[];
    value?: string;
    siteName?: string;
    disabled?: boolean;
  } = $props();

  const uid = $props.id();

  // Colours set through the CSSOM: the page's CSP allows no inline style attributes.
  function paint(node: HTMLElement, swatch: Swatch) {
    node.style.setProperty("--swatch-light", swatch.light);
    node.style.setProperty("--swatch-dark", swatch.dark);
  }
</script>

<fieldset class="picker" {disabled} aria-describedby={hint ? `${uid}-hint` : undefined}>
  <legend class="check-title">{legend}</legend>
  {#if hint}<p class="small muted" id="{uid}-hint">{hint}</p>{/if}
  <div class="options">
    {#if siteName !== undefined}
      <label class="option">
        <input type="radio" name={uid} value="" bind:group={value} />
        <span class="dot site" aria-hidden="true"></span>
        <span>Site's ({siteName})</span>
      </label>
    {/if}
    {#each swatches as swatch (swatch.key)}
      <label class="option">
        <input type="radio" name={uid} value={swatch.key} bind:group={value} />
        <span class="dot" use:paint={swatch} aria-hidden="true"></span>
        <span>{swatch.name}</span>
      </label>
    {/each}
  </div>
</fieldset>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    border: 0;
  }
  .picker:disabled {
    opacity: 0.6;
  }
  .options {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .option {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 40px;
    padding: 6px 12px 6px 8px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    font: var(--type-body-sm);
    cursor: pointer;
  }
  /* Invisible but on top of the dot, so a click lands on the radio itself. */
  .option input {
    position: absolute;
    margin: 0;
    opacity: 0;
  }
  .option:has(input:checked) {
    border-color: var(--text);
    box-shadow: inset 0 0 0 1px var(--text);
  }
  .option:has(input:focus-visible) {
    outline: 2px solid var(--link);
    outline-offset: 2px;
  }
  .dot {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--swatch-light);
    box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.15);
  }
  .dot.site {
    background: none;
    box-shadow: none;
    border: 2px dashed var(--border-strong);
  }
  :global(:root[data-theme="dark"]) .dot:not(.site) {
    background: var(--swatch-dark);
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme="light"])) .dot:not(.site) {
      background: var(--swatch-dark);
    }
  }
</style>
