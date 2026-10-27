<script lang="ts">
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
  const HEX = /^#[0-9A-Fa-f]{6}$/;

  function typed(event: Event & { currentTarget: HTMLInputElement }) {
    const text = event.currentTarget.value.trim();
    const hex = text.startsWith("#") ? text : `#${text}`;
    if (HEX.test(hex)) onchange(hex.toUpperCase());
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
    grid-template-columns: minmax(8rem, 1fr) 2.25rem 6.5rem minmax(7rem, auto);
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
