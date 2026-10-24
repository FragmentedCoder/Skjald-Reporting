<script lang="ts">
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import Info from "@lucide/svelte/icons/info";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import X from "@lucide/svelte/icons/x";
  import { onMount } from "svelte";
  import { dismiss, hold, release, toasts, type Toast } from "$lib/toast.svelte";

  let toaster: HTMLElement;

  // A popover sits in the browser's top layer, above the page and any dialog shown
  // before it. A dialog opened later covers it, so a new toast lifts it back up.
  onMount(() => toaster.showPopover());

  $effect(() => {
    if (toasts.length && document.querySelector("dialog[open]")) {
      toaster.hidePopover();
      toaster.showPopover();
    }
  });

  const ICONS = { ok: CircleCheck, info: Info, warning: TriangleAlert, critical: CircleAlert };

  function act(item: Toast) {
    item.action?.run();
    dismiss(item.id);
  }
</script>

<!-- Two live regions, always in the page, so screen readers announce what lands in
     them: urgent messages interrupt, the rest wait their turn. -->
<section class="toaster" aria-label="Notifications" popover="manual" bind:this={toaster}>
  {#each ["assertive", "polite"] as politeness (politeness)}
    <div class="region" aria-live={politeness === "assertive" ? "assertive" : "polite"}>
      {#each toasts.filter((t) => (t.tone === "critical") === (politeness === "assertive")) as item (item.id)}
        {@const Icon = ICONS[item.tone]}
        <div
          class="toast toast-{item.tone}"
          role={item.tone === "critical" ? "alert" : "status"}
          onmouseenter={() => hold(item.id)}
          onmouseleave={() => release(item.id)}
          onfocusin={() => hold(item.id)}
          onfocusout={() => release(item.id)}
        >
          <Icon class="icon" size={18} aria-hidden="true" />
          <div class="body">
            <p>{item.text}</p>
            {#if item.action}
              <button class="link-button" type="button" onclick={() => act(item)}>
                {item.action.label}
              </button>
            {/if}
          </div>
          <button class="close" type="button" aria-label="Dismiss" onclick={() => dismiss(item.id)}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      {/each}
    </div>
  {/each}
</section>

<style>
  /* Fixed in the corner and above everything; clicks go through wherever there's
     no toast. */
  .toaster {
    position: fixed;
    inset: auto var(--space-4) var(--space-4) auto;
    z-index: 2147483647;
    margin: 0;
    padding: 0;
    border: 0;
    overflow: visible;
    background: transparent;
    color: inherit;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: min(380px, calc(100vw - 2 * var(--space-4)));
    pointer-events: none;
  }
  .region {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .toast {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: start;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-left-width: 4px;
    border-radius: var(--radius-md);
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 8px 24px rgb(11 20 32 / 0.18);
    font: var(--type-body-sm);
    pointer-events: auto;
  }
  .toast :global(.icon) {
    margin-top: 1px;
  }
  .toast-ok {
    border-left-color: var(--ok-text);
  }
  .toast-ok :global(.icon) {
    color: var(--ok-text);
  }
  .toast-info {
    border-left-color: var(--info-text);
  }
  .toast-info :global(.icon) {
    color: var(--info-text);
  }
  .toast-warning {
    border-left-color: var(--warning-text);
  }
  .toast-warning :global(.icon) {
    color: var(--warning-text);
  }
  .toast-critical {
    border-left-color: var(--critical-text);
  }
  .toast-critical :global(.icon) {
    color: var(--critical-text);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .close {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    margin: -4px -4px 0 0;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .close:hover {
    background: var(--surface-subtle);
    color: var(--text);
  }
  @media (prefers-reduced-motion: no-preference) {
    .toast {
      animation: rise 160ms ease-out;
    }
    @keyframes rise {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
    }
  }
</style>
