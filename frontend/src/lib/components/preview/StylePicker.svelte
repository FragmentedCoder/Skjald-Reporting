<script lang="ts">
  import type { PreviewStyle } from "#lib/reportStyles/preview.svelte.js";

  // Which style the builder's preview is drawn in: the company's styles, or the Skjald default.
  let { looks }: { looks: PreviewStyle } = $props();

  function pick(event: Event & { currentTarget: HTMLSelectElement }) {
    const value = event.currentTarget.value;
    void looks.choose(value ? Number(value) : null);
  }
</script>

<label class="picker small">
  <span>Preview in</span>
  <select class="input" value={looks.chosen === null ? "" : String(looks.chosen)} onchange={pick}>
    <option value="">The Skjald default</option>
    {#each looks.choices as style (style.id)}
      <option value={String(style.id)}>{style.name}{style.is_default ? " (company default)" : ""}</option>
    {/each}
  </select>
</label>
{#if looks.problem}<p class="alert alert-warning small">{looks.problem}</p>{/if}

<style>
  .picker {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-3);
    color: var(--text-muted);
  }
  .picker select {
    width: auto;
    min-width: 12rem;
  }
</style>
