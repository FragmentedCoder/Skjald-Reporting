<script lang="ts">
  import type { Snippet } from "svelte";

  // An on/off setting: a checkbox that looks and announces itself as a switch.
  let {
    checked = $bindable(false),
    disabled = false,
    title,
    children,
  }: { checked?: boolean; disabled?: boolean; title: string; children?: Snippet } = $props();
</script>

<label class="switch" class:disabled>
  <input type="checkbox" role="switch" bind:checked {disabled} />
  <span class="track" aria-hidden="true"><span class="thumb"></span></span>
  <span class="text">
    <span class="switch-title">{title}</span>
    {#if children}<span class="small muted">{@render children()}</span>{/if}
  </span>
</label>

<style>
  .switch {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    cursor: pointer;
  }
  .switch.disabled {
    cursor: not-allowed;
  }
  input {
    position: absolute;
    width: 40px;
    height: 24px;
    margin: 0;
    opacity: 0;
    cursor: inherit;
  }
  .track {
    flex: none;
    position: relative;
    width: 40px;
    height: 24px;
    margin-top: 1px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-pill);
    background: var(--surface-subtle);
    transition: background 120ms;
    pointer-events: none; /* clicks reach the checkbox underneath */
  }
  .thumb {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--text-muted);
    transition: transform 120ms;
  }
  input:checked + .track {
    border-color: var(--link);
    background: var(--link);
  }
  input:checked + .track .thumb {
    background: var(--surface);
    transform: translateX(16px);
  }
  input:focus-visible + .track {
    outline: 2px solid var(--link);
    outline-offset: 2px;
  }
  input:disabled + .track {
    opacity: 0.55;
  }
  .text {
    display: flex;
    flex-direction: column;
  }
  .switch-title {
    font: var(--type-label);
  }
  @media (prefers-reduced-motion: reduce) {
    .track,
    .thumb {
      transition: none;
    }
  }
</style>
