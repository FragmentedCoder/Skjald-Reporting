<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import HeartPulse from "@lucide/svelte/icons/heart-pulse";
  import Palette from "@lucide/svelte/icons/palette";
  import ScrollText from "@lucide/svelte/icons/scroll-text";
  import ShieldCheck from "@lucide/svelte/icons/shield-check";
  import Users from "@lucide/svelte/icons/users";
  import { onMount, type Component, type Snippet } from "svelte";
  import AppShell from "$lib/components/AppShell.svelte";
  import type { Capability } from "$lib/roles";
  import { can, session, settle, type SessionInfo } from "$lib/session.svelte";

  let { children }: { children: Snippet } = $props();
  let info = $state<SessionInfo | null>(null);

  type Section =
    | "/admin/users"
    | "/admin/security"
    | "/admin/branding"
    | "/admin/health"
    | "/admin/audit";

  const SECTIONS: { path: Section; label: string; icon: Component; needs: Capability }[] = [
    { path: "/admin/users", label: "Users", icon: Users, needs: "administer" },
    { path: "/admin/security", label: "Security", icon: ShieldCheck, needs: "administer" },
    { path: "/admin/branding", label: "Branding", icon: Palette, needs: "administer" },
    { path: "/admin/health", label: "Server health", icon: HeartPulse, needs: "administer" },
    { path: "/admin/audit", label: "Audit log", icon: ScrollText, needs: "read_audit_log" },
  ];

  // The live session, so rights that change (a role, the allowlist) show at once.
  const current = $derived(session.current ?? info);
  const sections = $derived(SECTIONS.filter((s) => can(current, s.needs)));

  onMount(async () => {
    info = await settle("app");
  });
</script>

{#if info}
  <AppShell {info}>
    {#if sections.length}
      <div class="admin">
        <nav class="side" aria-label="Admin">
          {#each sections as section (section.path)}
            <a href={resolve(section.path)}
              aria-current={page.url.pathname.startsWith(section.path) ? "page" : undefined}>
              <section.icon size={18} aria-hidden="true" />
              {section.label}
            </a>
          {/each}
        </nav>
        <div class="main">{@render children()}</div>
      </div>
    {:else}
      <main class="page-content">
        <h1 class="title">Admin</h1>
        <p class="alert alert-warning">You don't have access to the admin panel.</p>
      </main>
    {/if}
  </AppShell>
{/if}

<style>
  .admin {
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr);
    gap: var(--space-6);
    width: 100%;
    max-width: 1280px;
    margin: 0 auto;
    padding: var(--space-8) var(--space-6);
  }
  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .side a {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font: var(--type-label);
    text-decoration: none;
  }
  .side a:hover,
  .side a[aria-current="page"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .main {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }
  @media (max-width: 800px) {
    .admin {
      grid-template-columns: 1fr;
      padding: var(--space-6) var(--space-4);
    }
    .side {
      flex-direction: row;
      flex-wrap: wrap;
    }
  }
</style>
