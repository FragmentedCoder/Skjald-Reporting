<script lang="ts">
  import { typedColour } from "#lib/reportStyles/resolve.js";

  // A style's colour: set here, or left to the style below (shown as the value it gives).
  let {
    id,
    label,
    value,
    inherited,
    readonly = false,
    onchange,
  }: {
    id: string;
    label: string;
    value: string | null | undefined;
    inherited: string;
    readonly?: boolean;
    onchange: (value: string | null) => void;
  } = $props();

  const shown = $derived((value ?? inherited).toUpperCase());

  // What's typed is a colour or it's taken back: left in the box, it would read as the
  // style's colour beside a swatch (and a report) that still show the old one.
  function typed(event: Event & { currentTarget: HTMLInputElement }) {
    const hex = typedColour(event.currentTarget.value);
    if (hex) onchange(hex);
    event.currentTarget.value = hex ?? shown;
  }
</script>

<div class="colour">
  <label for={id}>{label}</label>
  <input class="swatch" type="color" aria-label="{label}: pick a colour" value={shown.toLowerCase()} disabled={readonly}
    oninput={(e) => onchange(e.currentTarget.value.toUpperCase())} />
  <input {id} class="input mono hex" value={shown} maxlength="7" disabled={readonly} onchange={typed} />
  {#if value}
    <button class="link-button small" type="button" disabled={readonly} onclick={() => onchange(null)}>Use the one below</button>
  {:else}
    <span class="small muted">From the one below</span>
  {/if}
</div>

<style>
  .colour {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 2.25rem 6.5rem 8.5rem;
    align-items: center;
    gap: var(--space-2);
  }
  .swatch {
    width: 2.25rem;
    height: 2.25rem;
    padding: 2px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
  }
  .hex {
    text-transform: uppercase;
  }
</style>
