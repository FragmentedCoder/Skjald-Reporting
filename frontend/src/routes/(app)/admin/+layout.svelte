<script lang="ts">
  import type { Snippet } from "svelte";
  import { can, session } from "#lib/session.svelte.js";

  // The admin panel's pages. Their sections are in the side menu, under Admin.
  let { children }: { children: Snippet } = $props();

  // The live session, so rights that change (a role, the allowlist) show at once.
  const allowed = $derived(
    can(session.current, "administer") || can(session.current, "read_audit_log"),
  );
</script>

{#if allowed}
  <main class="page-content wide">{@render children()}</main>
{:else}
  <main class="page-content">
    <h1 class="title">Admin</h1>
    <p class="alert alert-warning">You don't have access to the admin panel.</p>
  </main>
{/if}

<style>
  .wide {
    max-width: 1180px;
  }
</style>
