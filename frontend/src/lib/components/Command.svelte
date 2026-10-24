<script lang="ts">
  import Copy from "@lucide/svelte/icons/copy";
  import { toast } from "$lib/toast.svelte";

  // A shell command to run on the server, set apart so it can't be missed, with a
  // button that copies it.
  let { command }: { command: string } = $props();

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      toast("Command copied.", "ok", { key: "copied" });
    } catch {
      toast("Couldn't copy. Select the command and copy it yourself.", "warning");
    }
  }
</script>

<div class="command">
  <code><strong>{command}</strong></code>
  <button class="button button-secondary" type="button" onclick={copy}>
    <Copy size={16} aria-hidden="true" />
    Copy<span class="visually-hidden"> command</span>
  </button>
</div>

<style>
  .command {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border-strong);
    border-left: 4px solid var(--accent);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  code {
    flex: 1;
    min-width: 0;
    font: var(--type-code);
    overflow-wrap: anywhere;
  }
  strong {
    font-weight: 600;
  }
</style>
