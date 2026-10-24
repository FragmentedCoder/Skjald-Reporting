<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import House from "@lucide/svelte/icons/house";
  import LogOut from "@lucide/svelte/icons/log-out";
  import Shield from "@lucide/svelte/icons/shield-check";
  import type { Snippet } from "svelte";
  import Avatar from "./Avatar.svelte";
  import Brand from "./Brand.svelte";
  import { can, session, signOut, type SessionInfo } from "$lib/session.svelte";

  let { info, children }: { info: SessionInfo; children: Snippet } = $props();

  // The live session when there is one, so a new name or picture shows at once.
  const user = $derived((session.current ?? info).user);
  const current = $derived(session.current ?? info);
  const showAdmin = $derived(can(current, "administer") || can(current, "read_audit_log"));
  const path = $derived(page.url.pathname);
</script>

<header class="bar">
  <a class="home" href={resolve("/")} aria-label="Home">
    <Brand size={32} />
  </a>
  <nav class="nav" aria-label="Main">
    <a href={resolve("/")} aria-current={path === "/" ? "page" : undefined}>
      <House size={16} aria-hidden="true" />
      Home
    </a>
    {#if showAdmin}
      <a href={resolve("/admin")} aria-current={path.startsWith("/admin") ? "page" : undefined}>
        <Shield size={16} aria-hidden="true" />
        Admin
      </a>
    {/if}
  </nav>
  <div class="who">
    <a class="account" href={resolve("/account")} title="Your account: {user.display_name}"
      aria-current={path === "/account" ? "page" : undefined}>
      <Avatar name={user.display_name} url={user.avatar_url} size={28} />
      <span class="name">{user.display_name}</span>
      <span class="visually-hidden">, your account</span>
    </a>
    <button class="button button-secondary" type="button" onclick={signOut}>
      <LogOut size={16} aria-hidden="true" />
      Sign out
    </button>
  </div>
</header>

{@render children()}

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-6);
    padding: var(--space-3) var(--space-6);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .home {
    min-width: 0;
    max-width: 280px;
    color: var(--text);
    text-decoration: none;
  }
  .nav {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    flex: 1;
  }
  .nav a,
  .account {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font: var(--type-label);
    text-decoration: none;
  }
  .nav a:hover,
  .nav a[aria-current="page"],
  .account:hover,
  .account[aria-current="page"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .who {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .account {
    min-width: 0;
    min-height: 44px;
    padding-left: 8px;
  }
  /* Long names are cut short; the full name is in the tooltip and on the page. */
  .name {
    max-width: 16ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  @media (max-width: 640px) {
    .bar {
      padding-inline: var(--space-4);
    }
    .nav {
      order: 3;
      flex-basis: 100%;
    }
    .who {
      margin-left: auto;
    }
    .name {
      max-width: 10ch;
    }
  }
</style>
