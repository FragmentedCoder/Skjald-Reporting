<script lang="ts">
  import { afterNavigate } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Archive from "@lucide/svelte/icons/archive";
  import Contact from "@lucide/svelte/icons/contact";
  import FileText from "@lucide/svelte/icons/file-text";
  import FolderKanban from "@lucide/svelte/icons/folder-kanban";
  import HeartPulse from "@lucide/svelte/icons/heart-pulse";
  import House from "@lucide/svelte/icons/house";
  import LayoutDashboard from "@lucide/svelte/icons/layout-dashboard";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import LogOut from "@lucide/svelte/icons/log-out";
  import Menu from "@lucide/svelte/icons/menu";
  import Moon from "@lucide/svelte/icons/moon";
  import Palette from "@lucide/svelte/icons/palette";
  import ScrollText from "@lucide/svelte/icons/scroll-text";
  import Settings from "@lucide/svelte/icons/settings";
  import Shield from "@lucide/svelte/icons/shield-check";
  import Building from "@lucide/svelte/icons/building";
  import Sun from "@lucide/svelte/icons/sun";
  import Users from "@lucide/svelte/icons/users";
  import UsersRound from "@lucide/svelte/icons/users-round";
  import X from "@lucide/svelte/icons/x";
  import { onMount, type Component, type Snippet } from "svelte";
  import { api } from "#lib/api.js";
  import { classificationTone, type ProjectSummary } from "#lib/customers.js";
  import { applyTheme, can, session, signOut, type SessionInfo } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";
  import { clearWorkspace, openCustomer, refreshWorkspace, workspace } from "#lib/workspace.svelte.js";
  import Avatar from "./Avatar.svelte";
  import Brand from "./Brand.svelte";
  import CustomerPicker from "./CustomerPicker.svelte";

  // The app's frame: a side menu with the customer you're working in, its
  // projects, and the open project's sections; the page beside it. On a narrow
  // screen the menu slides in from a button in a slim top bar.
  let { info, children }: { info: SessionInfo; children: Snippet } = $props();

  interface Item {
    href: string;
    label: string;
    icon: Component<{ size?: number; "aria-hidden"?: boolean | "true" }>;
    current: boolean;
    count?: number | null;
  }

  const current = $derived(session.current ?? info);
  const user = $derived(current.user);
  const path = $derived(page.url.pathname);
  const customer = $derived(openCustomer());
  const full = $derived(customer?.visibility === "full");
  const showAdmin = $derived(can(current, "administer") || can(current, "read_audit_log"));
  const sees = $derived(current.user.roles.length > 0);
  let menuOpen = $state(false);

  const customerItems = $derived.by((): Item[] => {
    if (!customer || !full) return [];
    const id = String(customer.id);
    const base = resolve("/(app)/customers/[id]", { id });
    return [
      { href: base, label: "Overview", icon: LayoutDashboard, current: path === base },
      { href: resolve("/(app)/customers/[id]/projects", { id }), label: "Projects", icon: FolderKanban,
        current: path === resolve("/(app)/customers/[id]/projects", { id }), count: customer.active_projects },
      { href: resolve("/(app)/customers/[id]/archived", { id }), label: "Archived", icon: Archive,
        current: path === resolve("/(app)/customers/[id]/archived", { id }), count: customer.archived_projects },
      { href: resolve("/(app)/customers/[id]/contacts", { id }), label: "Contacts & sites", icon: Contact,
        current: path === resolve("/(app)/customers/[id]/contacts", { id }) },
      { href: resolve("/(app)/customers/[id]/people", { id }), label: "People", icon: UsersRound,
        current: path === resolve("/(app)/customers/[id]/people", { id }) },
    ];
  });

  // The customer's own settings (details, logo, deleting it), for Administrators:
  // last in the customer's part of the menu, just above Home.
  const customerSettings = $derived.by((): Item | null => {
    if (!customer || !full || !can(current, "manage_customers")) return null;
    const href = resolve("/(app)/customers/[id]/settings", { id: String(customer.id) });
    return { href, label: "Customer settings", icon: Settings, current: path === href };
  });

  // The open project's own sections, shown under it in the list.
  function projectItems(projectId: number): Item[] {
    const id = String(projectId);
    return [
      { href: resolve("/(app)/projects/[id]", { id }), label: "Reports", icon: FileText,
        current: path === resolve("/(app)/projects/[id]", { id }) },
      { href: resolve("/(app)/projects/[id]/details", { id }), label: "Details", icon: ListChecks,
        current: path === resolve("/(app)/projects/[id]/details", { id }) },
      { href: resolve("/(app)/projects/[id]/team", { id }), label: "Team", icon: Users,
        current: path === resolve("/(app)/projects/[id]/team", { id }) },
    ];
  }

  const adminItems = $derived.by((): Item[] => {
    const items: Item[] = [];
    const add = (route: `/(app)/admin/${"users" | "security" | "branding" | "health" | "audit"}`,
                 label: string, icon: Item["icon"]) =>
      items.push({ href: resolve(route), label, icon, current: path.startsWith(resolve(route)) });
    if (can(current, "administer")) {
      add("/(app)/admin/users", "Users", Users);
      add("/(app)/admin/security", "Security", Shield);
      add("/(app)/admin/branding", "Branding", Palette);
      add("/(app)/admin/health", "Server health", HeartPulse);
    }
    if (can(current, "read_audit_log")) add("/(app)/admin/audit", "Audit log", ScrollText);
    return items;
  });

  // Light or dark right now: the person's choice, or the device's when "system".
  let deviceDark = $state(false);
  const dark = $derived(user.theme === "dark" || (user.theme === "system" && deviceDark));

  onMount(() => {
    void refreshWorkspace();
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    deviceDark = query.matches;
    const changed = () => (deviceDark = query.matches);
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  });

  // Moving to another page closes the menu on a phone.
  afterNavigate(() => (menuOpen = false));

  async function toggleTheme() {
    const next = dark ? "light" : "dark";
    applyTheme(next);
    if (session.current) session.current.user.theme = next;
    try {
      await api("PATCH", "/account", { theme: next });
    } catch {
      toast("Couldn't save the change; it lasts until you reload.", "warning", { key: "theme" });
    }
  }

  async function leave() {
    clearWorkspace();
    await signOut();
  }
</script>

{#snippet link(item: Item, depth = 0)}
  <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- every item's href comes from resolve() -->
  <a class="item depth-{depth}" href={item.href} aria-current={item.current ? "page" : undefined}>
    <item.icon size={16} aria-hidden="true" />
    <span class="text">{item.label}</span>
    {#if item.count !== undefined && item.count !== null}<span class="count">{item.count}</span>{/if}
  </a>
{/snippet}

{#snippet projectEntry(project: ProjectSummary)}
  {@const open = project.id === workspace.project?.id}
  {@const href = resolve("/(app)/projects/[id]", { id: String(project.id) })}
  <a class="item depth-1 project" {href} class:open>
    <span class="dot {classificationTone(project.classification)}" aria-hidden="true"></span>
    <span class="text">{project.name}</span>
    <span class="visually-hidden">, {project.classification}</span>
  </a>
  {#if open}
    <ul class="items nested">
      {#each projectItems(project.id) as sub (sub.href)}
        <li>{@render link(sub, 2)}</li>
      {/each}
    </ul>
  {/if}
{/snippet}

<svelte:window onkeydown={(event) => {
  if (menuOpen && event.key === "Escape") menuOpen = false;
}} />

<div class="frame" class:menu-open={menuOpen}>
  <header class="topbar">
    <button class="icon-button" type="button" aria-label="Open the menu" aria-expanded={menuOpen}
      aria-controls="side-menu" onclick={() => (menuOpen = true)}>
      <Menu size={20} aria-hidden="true" />
    </button>
    <a class="home" href={resolve("/(app)")}><Brand size={28} /></a>
  </header>

  {#if menuOpen}
    <button class="scrim" type="button" aria-label="Close the menu" onclick={() => (menuOpen = false)}></button>
  {/if}

  <aside class="side" id="side-menu" aria-label="Side menu">
    <div class="side-head">
      <a class="home" href={resolve("/(app)")}><Brand size={30} /></a>
      <button class="icon-button close" type="button" aria-label="Close the menu"
        onclick={() => (menuOpen = false)}>
        <X size={20} aria-hidden="true" />
      </button>
    </div>

    <nav class="nav" aria-label="Main">
      {#if sees}
        <CustomerPicker />
        {#if customer && full}
          <ul class="items">
            {#each customerItems as item (item.href)}
              <li>
                {@render link(item)}
                {#if item.label === "Projects" && workspace.projects?.length}
                  <ul class="items nested">
                    {#each workspace.projects as project (project.id)}
                      <li>{@render projectEntry(project)}</li>
                    {/each}
                  </ul>
                {:else if item.label === "Archived" && workspace.project?.archived_at}
                  <ul class="items nested">
                    <li>{@render projectEntry(workspace.project)}</li>
                  </ul>
                {/if}
              </li>
            {/each}
          </ul>
          {#if customerSettings}
            <ul class="items customer-foot">
              <li>{@render link(customerSettings)}</li>
            </ul>
          {/if}
        {:else if customer}
          <p class="small muted hint">
            {customer.visibility === "names" ? "You see this customer's name only." : "You see an overview of this customer."}
          </p>
        {:else}
          <p class="small muted hint">Choose a customer to see its projects, contacts and people.</p>
        {/if}
      {/if}

      <ul class="items global">
        <li>{@render link({ href: resolve("/(app)"), label: "Home", icon: House, current: path === "/" })}</li>
        {#if sees}
          <li>{@render link({ href: resolve("/(app)/customers"), label: "All customers", icon: Building,
            current: path === "/customers" || path === "/customers/new" })}</li>
        {/if}
        {#if showAdmin}
          <li>
            {@render link({ href: resolve("/(app)/admin"), label: "Admin", icon: Shield,
              current: path === "/admin" })}
            {#if path.startsWith("/admin")}
              <ul class="items nested">
                {#each adminItems as item (item.href)}
                  <li>{@render link(item, 1)}</li>
                {/each}
              </ul>
            {/if}
          </li>
        {/if}
      </ul>
    </nav>

    <div class="you">
      <a class="account" href={resolve("/(app)/account")} title="Your account: {user.display_name}"
        aria-current={path === "/account" ? "page" : undefined}>
        <Avatar name={user.display_name} url={user.avatar_url} size={32} />
        <span class="name">{user.display_name}</span>
        <span class="visually-hidden">, your account</span>
      </a>
      <button class="icon-button" type="button" onclick={toggleTheme}
        aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
        title={dark ? "Switch to light mode" : "Switch to dark mode"}>
        {#if dark}<Sun size={18} aria-hidden="true" />{:else}<Moon size={18} aria-hidden="true" />{/if}
      </button>
      <button class="icon-button" type="button" onclick={leave} aria-label="Sign out" title="Sign out">
        <LogOut size={18} aria-hidden="true" />
      </button>
    </div>
  </aside>

  <div class="content">
    {@render children()}
  </div>
</div>

<style>
  .frame {
    display: grid;
    /* Wide enough for the customer picker's search and list under its button. */
    grid-template-columns: 284px minmax(0, 1fr);
    min-height: 100vh;
  }
  .topbar,
  .scrim,
  .icon-button.close {
    display: none;
  }
  .side {
    position: sticky;
    top: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    height: 100vh;
    padding: var(--space-4) var(--space-3);
    overflow-y: auto;
    border-right: 1px solid var(--border);
    background: var(--surface);
  }
  .side-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--space-1);
  }
  .home {
    min-width: 0;
    color: var(--text);
    text-decoration: none;
  }
  .nav {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-3);
  }
  .items {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .nested {
    margin-top: 2px;
  }
  .global {
    margin-top: auto;
    padding-top: var(--space-3);
    border-top: 1px solid var(--border);
  }
  .customer-foot {
    margin-top: auto;
  }
  .customer-foot + .global {
    margin-top: 0;
  }
  .item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 36px;
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font: var(--type-label);
    text-decoration: none;
  }
  .item:hover {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .item[aria-current="page"] {
    background: var(--surface-subtle);
    color: var(--text);
    box-shadow: inset 3px 0 0 var(--accent);
  }
  .depth-1 {
    padding-left: 30px;
    font: var(--type-body-sm);
  }
  .depth-2 {
    padding-left: 48px;
    font: var(--type-body-sm);
  }
  .project.open {
    color: var(--text);
    font-weight: 600;
  }
  .text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    min-width: 22px;
    padding: 0 6px;
    border-radius: var(--radius-pill);
    background: var(--surface-subtle);
    font: var(--type-body-sm);
    text-align: center;
  }
  /* A TLP colour by each project, red for the most restricted. */
  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--border-strong);
  }
  .dot.critical {
    background: var(--critical-text);
  }
  .dot.warning {
    background: var(--warning-text);
  }
  .dot.ok {
    background: var(--ok-text);
  }
  .hint {
    padding: 0 var(--space-2);
  }
  .you {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding-top: var(--space-3);
    border-top: 1px solid var(--border);
  }
  .account {
    display: flex;
    flex: 1;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    min-height: 44px;
    padding: 4px 8px;
    border-radius: var(--radius-sm);
    color: var(--text);
    font: var(--type-label);
    text-decoration: none;
  }
  .account:hover,
  .account[aria-current="page"] {
    background: var(--surface-subtle);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .icon-button {
    display: grid;
    flex: none;
    place-items: center;
    width: 40px;
    height: 40px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .icon-button:hover {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .content {
    min-width: 0;
  }

  /* Narrow screens: a slim top bar, and the menu slides in over the page. */
  @media (max-width: 900px) {
    .frame {
      grid-template-columns: 1fr;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-2) var(--space-3);
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    .side {
      position: fixed;
      inset: 0 auto 0 0;
      z-index: 40;
      width: min(300px, 86vw);
      /* Hidden, not only moved away, so a closed menu is out of the tab order. */
      visibility: hidden;
      transform: translateX(-105%);
      transition:
        transform 160ms ease-out,
        visibility 0s linear 160ms;
    }
    .menu-open .side {
      visibility: visible;
      transform: none;
      box-shadow: 0 8px 32px rgb(11 20 32 / 0.3);
      transition: transform 160ms ease-out;
    }
    .scrim {
      display: block;
      position: fixed;
      inset: 0;
      z-index: 30;
      border: 0;
      background: rgb(11 20 32 / 0.45);
    }
    .icon-button.close {
      display: grid;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .side,
    .menu-open .side {
      transition: none;
    }
  }
</style>
