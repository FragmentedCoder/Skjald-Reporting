<script lang="ts">
  import type { Snippet } from "svelte";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { pageTitle } from "#lib/branding.svelte.js";
  import { can, session } from "#lib/session.svelte.js";

  // The Database: every name a template can read, to look up and try; the shared
  // library's variables, text snippets and data tables; and custom fields. Each tab
  // for those who may use it.
  let { children }: { children: Snippet } = $props();

  const tabs = $derived([
    { href: resolve("/(app)/database"), label: "All names", shown: true },
    { href: resolve("/(app)/database/variables"), label: "Variables", shown: can(session.current, "edit_library") },
    { href: resolve("/(app)/database/snippets"), label: "Text snippets", shown: can(session.current, "edit_library") },
    { href: resolve("/(app)/database/tables"), label: "Data tables", shown: can(session.current, "edit_library") },
    { href: resolve("/(app)/database/custom-fields"), label: "Custom fields", shown: can(session.current, "build_templates") },
  ].filter((t) => t.shown));
  const here = $derived(tabs.find((t) => t.href === page.url.pathname)?.label);
</script>

<svelte:head><title>{pageTitle(here && here !== "All names" ? `${here} · Database` : "Database")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Database</h1>
      <p class="small muted">Everything a template can read: the report's details, the company's custom fields, and the library shared by every template and report.</p>
    </div>
  </div>
  <nav class="tabs" aria-label="Database">
    {#each tabs as tab (tab.href)}
      <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- every tab's href comes from resolve() -->
      <a href={tab.href} aria-current={page.url.pathname === tab.href ? "page" : undefined}>{tab.label}</a>
    {/each}
  </nav>
  {@render children()}
</main>

<style>
  .tabs {
    display: flex;
    gap: var(--space-1);
    margin-top: calc(-1 * var(--space-3));
    overflow-x: auto;
    border-bottom: 1px solid var(--border);
  }
  .tabs a {
    padding: var(--space-2) var(--space-3);
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 14px;
    text-decoration: none;
    white-space: nowrap;
  }
  .tabs a:hover {
    color: var(--text);
  }
  .tabs a[aria-current="page"] {
    border-bottom-color: var(--link);
    color: var(--text);
  }
</style>
