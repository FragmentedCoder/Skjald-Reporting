<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Archive from "@lucide/svelte/icons/archive";
  import ArchiveRestore from "@lucide/svelte/icons/archive-restore";
  import FolderKanban from "@lucide/svelte/icons/folder-kanban";
  import { untrack, type Snippet } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import RecordHeader from "#lib/components/RecordHeader.svelte";
  import { shareCustomer, shareProject } from "#lib/context.js";
  import { classificationTone, type CustomerDetail, type ProjectDetail } from "#lib/customers.js";
  import { dateTime } from "#lib/format.js";
  import { toast } from "#lib/toast.svelte.js";
  import { chooseCustomer, refreshWorkspace, workspace } from "#lib/workspace.svelte.js";

  // A project's pages share this: the project, its header with archiving, and the
  // side menu opened on its customer and on it. Those who may change the project
  // also get its customer, to pick the responsible, contact, sites and team from.
  let { children }: { children: Snippet } = $props();

  let project = $state<ProjectDetail | null>(null);
  let customer = $state<CustomerDetail | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let archiveOpen = $state(false);

  const id = $derived(page.params.id ?? "");
  const customerId = $derived(project?.customer.id);
  const editable = $derived(project?.may_edit ?? false);

  let leaving = false;
  let checked = workspace.checks;

  // Access that ends while the project is open (you're taken off its team or
  // the customer, it's deleted): back to its customer, or to your customers.
  async function lost(name: string) {
    if (leaving) return;
    leaving = true;
    toast(`You no longer have access to ${name}.`, "warning", { key: "access" });
    const customerId = project?.customer.id;
    await refreshWorkspace();
    const back = workspace.customers?.find((c) => c.id === customerId && c.visibility === "full");
    await goto(back
      ? resolve("/(app)/customers/[id]", { id: String(back.id) })
      : resolve("/(app)/customers"), { replace: true });
  }

  async function load() {
    const known = project?.id === Number(id) ? project.name : null;
    try {
      project = await api<ProjectDetail>("GET", `/projects/${id}`);
      error = null;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && known) {
        void lost(known);
        return;
      }
      project = null;
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not found.";
    }
  }

  // Each time the menu refreshes, check the project is still yours to open. Only
  // a refusal counts: the page keeps what it has, so nothing being typed is lost.
  $effect(() => {
    const now = workspace.checks;
    if (now === checked || !project) return;
    checked = now;
    const name = project.name;
    api("GET", `/projects/${id}`).catch((e) => {
      if (e instanceof ApiError && e.status === 404) void lost(name);
    });
  });

  shareProject({
    get current() {
      return project;
    },
    use(found) {
      project = found;
      void refreshWorkspace();
    },
    async reload() {
      await load();
      await refreshWorkspace();
    },
  });

  shareCustomer({
    get current() {
      return customer;
    },
    use(found) {
      customer = found;
    },
    async reload() {
      if (customerId !== undefined) customer = await api<CustomerDetail>("GET", `/customers/${customerId}`);
    },
  });

  $effect(() => {
    void id;
    // Only the ID counts: what loading reads (the project so far) mustn't start it again.
    untrack(() => {
      leaving = false;
      void load();
    });
  });

  // Opens the project's customer, and the project under it, in the side menu. Only
  // the project counts, not the menu's state that choosing reads.
  $effect(() => {
    const open = project;
    if (open) untrack(() => void chooseCustomer(open.customer.id, open));
  });

  $effect(() => {
    const wanted = customerId;
    if (wanted === undefined || !editable) {
      customer = null;
      return;
    }
    api<CustomerDetail>("GET", `/customers/${wanted}`)
      .then((found) => (customer = found))
      .catch((e) => {
        if (!sessionGone(e)) customer = null;
      });
  });

  async function run(action: () => Promise<ProjectDetail>, done: string) {
    busy = true;
    try {
      project = await action();
      toast(done, "ok", { key: "saved" });
      await refreshWorkspace();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "Something went wrong. Try again.", "critical");
    } finally {
      busy = false;
    }
  }

  function archive() {
    archiveOpen = false;
    run(() => api("POST", `/projects/${id}/archive`), "Archived: the project is read-only now.");
  }
</script>

<main class="page-content">
  {#if error}
    <div>
      <a class="small" href={resolve("/(app)")}>Home</a>
      <p class="alert alert-critical" role="alert">{error}</p>
    </div>
  {:else if project}
    <div class="page-header">
      <RecordHeader kind="Project" title={project.name} icon={FolderKanban}>
        <div class="tags">
          <span class="small muted mono">{project.number}</span>
          <Pill tone={classificationTone(project.classification)} text={project.classification} />
          {#if project.archived_at}<Pill tone="neutral" text="Archived" />{/if}
          <span class="small muted">
            for <a href={resolve("/(app)/customers/[id]", { id: String(project.customer.id) })}>{project.customer.name}</a>
          </span>
        </div>
      </RecordHeader>
      {#if project.may_edit}
        <button class="button button-secondary" type="button" disabled={busy}
          onclick={() => (archiveOpen = true)}>
          <Archive size={16} aria-hidden="true" />Archive project
        </button>
      {:else if project.may_reopen}
        <button class="button button-secondary" type="button" disabled={busy}
          onclick={() => run(() => api("POST", `/projects/${id}/reopen`), "Reopened: the project can be changed again.")}>
          <ArchiveRestore size={16} aria-hidden="true" />Reopen project
        </button>
      {/if}
    </div>

    {#if project.archived_at}
      <p class="alert alert-info">
        Archived {dateTime(project.archived_at)}. The project and its reports are read-only, and
        retention periods count from this date.
      </p>
    {/if}

    {@render children()}
  {/if}
</main>

<Dialog bind:open={archiveOpen} title="Archive {project?.number ?? 'project'}">
  <p>
    The project and its reports become read-only, and it moves to the customer's archived
    projects. Retention periods count from today. A Manager or Administrator can reopen it.
  </p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (archiveOpen = false)}>Cancel</button>
    <button class="button button-primary" type="button" onclick={archive}>Archive project</button>
  {/snippet}
</Dialog>

<style>
  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-1);
  }
</style>
