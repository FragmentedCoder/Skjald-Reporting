<script lang="ts" module>
  import type { Component } from "svelte";

  export interface MenuItem {
    label: string;
    icon?: Component<{ size?: number; "aria-hidden"?: boolean | "true" }>;
    run: () => void;
    danger?: boolean;
  }
</script>

<script lang="ts">
  import EllipsisVertical from "@lucide/svelte/icons/ellipsis-vertical";
  import { tick } from "svelte";

  // A "⋮" button with a short menu of actions for one row. The menu is a popover:
  // the browser closes it on Escape or a click elsewhere, and it isn't clipped by
  // a scrolling table.
  let { label, items }: { label: string; items: MenuItem[] } = $props();

  const uid = $props.id();
  let button: HTMLButtonElement;
  let menu: HTMLDivElement;
  let expanded = $state(false);

  function place() {
    const box = button.getBoundingClientRect();
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const below = box.bottom + 4 + height <= window.innerHeight;
    menu.style.top = `${below ? box.bottom + 4 : Math.max(box.top - 4 - height, 8)}px`;
    menu.style.left = `${Math.max(Math.min(box.right - width, window.innerWidth - width - 8), 8)}px`;
  }

  // Hidden until placed beside its button, so it never shows up in the wrong spot.
  function opening(event: ToggleEvent) {
    if (event.newState === "open") menu.style.visibility = "hidden";
  }

  async function toggled(event: ToggleEvent) {
    expanded = event.newState === "open";
    if (!expanded) return;
    place();
    menu.style.visibility = "visible";
    await tick();
    menu.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus();
  }

  function choose(item: MenuItem) {
    menu.hidePopover();
    button.focus();
    item.run();
  }

  function keys(event: KeyboardEvent) {
    const entries = [...menu.querySelectorAll<HTMLButtonElement>("[role=menuitem]")];
    const at = entries.indexOf(document.activeElement as HTMLButtonElement);
    const moves: Record<string, number> = {
      ArrowDown: (at + 1) % entries.length,
      ArrowUp: (at - 1 + entries.length) % entries.length,
      Home: 0,
      End: entries.length - 1,
    };
    if (event.key in moves) {
      event.preventDefault();
      entries[moves[event.key]]?.focus();
    } else if (event.key === "Tab") {
      menu.hidePopover();
    }
  }
</script>

<button
  bind:this={button}
  class="trigger"
  type="button"
  aria-label={label}
  aria-haspopup="menu"
  aria-expanded={expanded}
  aria-controls="{uid}-menu"
  popovertarget="{uid}-menu"
>
  <EllipsisVertical size={18} aria-hidden="true" />
</button>

<div
  bind:this={menu}
  id="{uid}-menu"
  class="menu"
  role="menu"
  aria-label={label}
  popover="auto"
  tabindex="-1"
  onbeforetoggle={opening}
  ontoggle={toggled}
  onkeydown={keys}
>
  {#each items as item (item.label)}
    <button class="item" class:danger={item.danger} type="button" role="menuitem"
      tabindex="-1" onclick={() => choose(item)}>
      {#if item.icon}<item.icon size={16} aria-hidden="true" />{/if}
      {item.label}
    </button>
  {/each}
</div>

<style>
  .trigger {
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .trigger:hover,
  .trigger[aria-expanded="true"] {
    border-color: var(--border);
    background: var(--surface-subtle);
    color: var(--text);
  }
  .menu {
    position: fixed;
    inset: auto;
    min-width: 220px;
    margin: 0;
    padding: var(--space-1);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 8px 24px rgb(11 20 32 / 0.18);
  }
  .item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: 40px;
    padding: 8px 12px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text);
    font: var(--type-body-sm);
    text-align: left;
    cursor: pointer;
  }
  .item:hover,
  .item:focus-visible {
    background: var(--surface-subtle);
    outline: none;
  }
  .item.danger {
    color: var(--critical-text);
  }
</style>
