<script lang="ts">
  import type { PreviewStyle } from "#lib/reportStyles/preview.svelte.js";

  // Which style the builder's preview is drawn in: the company's styles, or the Skjald
  // default. Only the preview changes: a report is printed in its customer's style. It
  // sits at the end of the preview's title line; the page shows looks.problem itself.
  let { looks }: { looks: PreviewStyle } = $props();

  function pick(event: Event & { currentTarget: HTMLSelectElement }) {
    const value = event.currentTarget.value;
    void looks.choose(value ? Number(value) : null);
  }
</script>

<label class="picker small" title="The report style the preview is drawn in: its colours, fonts, page designs and logos. Only the preview changes; a report is printed in its customer's style.">
  <span>Preview in</span>
  <select class="input" value={looks.chosen === null ? "" : String(looks.chosen)} onchange={pick}>
    <option value="">The Skjald default</option>
    {#each looks.choices as style (style.id)}
      <option value={String(style.id)}>{style.name}{style.is_default ? " (company default)" : ""}</option>
    {/each}
  </select>
</label>

<style>
  .picker {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-muted);
  }
  /* Compact, to sit in a title line beside other small controls. */
  .picker select {
    width: auto;
    min-width: 12rem;
    min-height: 0;
    height: 34px;
    padding-top: 0;
    padding-bottom: 0;
    font-size: 13px;
  }
</style>
