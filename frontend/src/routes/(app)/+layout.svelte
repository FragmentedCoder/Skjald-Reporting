<script lang="ts">
  import { onMount, type Snippet } from "svelte";
  import AppShell from "#lib/components/AppShell.svelte";
  import { settle, type SessionInfo } from "#lib/session.svelte.js";

  // Every page for someone signed in: the session is settled once, here, and the
  // side menu stays put while the pages beside it change.
  let { children }: { children: Snippet } = $props();
  let info = $state<SessionInfo | null>(null);

  onMount(async () => {
    info = await settle("app");
  });
</script>

{#if info}
  <AppShell {info}>{@render children()}</AppShell>
{/if}
