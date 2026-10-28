<script lang="ts">
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import CustomFieldValues from "#lib/components/CustomFieldValues.svelte";
  import ProjectFields, { projectBody, type ProjectForm } from "#lib/components/ProjectFields.svelte";
  import { sharedCustomer, sharedProject } from "#lib/context.js";
  import type { ProjectDetail } from "#lib/customers.js";
  import { dateRange, dateTime } from "#lib/format.js";
  import { toast } from "#lib/toast.svelte.js";

  // What a project is: its name, dates, who's responsible, the contact and sites,
  // and how it's shared. Changed by those who may change the customer's projects.
  const shared = sharedProject();
  const project = $derived(shared.current);
  const customer = $derived(sharedCustomer().current);
  let form = $state<ProjectForm | null>(null);
  let busy = $state(false);
  let error = $state<string | null>(null);

  $effect(() => {
    if (!project) return;
    form = {
      name: project.name,
      start_date: project.start_date ?? "",
      end_date: project.end_date ?? "",
      responsible_id: project.responsible ? String(project.responsible.id) : "",
      reviewer_id: project.reviewer ? String(project.reviewer.id) : "",
      contact_id: project.contact ? String(project.contact.id) : "",
      site_ids: project.sites.map((s) => s.id),
      classification: project.classification,
      custom: { ...project.custom },
    };
  });

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!form || !project) return;
    busy = true;
    error = null;
    try {
      shared.use(await api<ProjectDetail>("PATCH", `/projects/${project.id}`, projectBody(form)));
      toast("Project saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle(project ? `Details · ${project.number}` : "Project")}</title></svelte:head>

{#if project?.may_edit && form && customer}
  <section class="section" aria-labelledby="edit-title">
    <h2 class="section-title" id="edit-title">Details</h2>
    <p class="small muted">Reports fill these in. Changes are logged.</p>
    <form class="stack form-wide" onsubmit={save}>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      <ProjectFields bind:values={form} {customer} />
      <div><button class="button button-primary" type="submit" disabled={busy}>Save project</button></div>
    </form>
  </section>
{:else if project}
  <section class="section" aria-labelledby="facts-title">
    <h2 class="section-title" id="facts-title">Details</h2>
    <dl class="facts">
      <dt>Responsible</dt>
      <dd>{project.responsible?.name ?? "Nobody yet"}</dd>
      <dt>Reviewer</dt>
      <dd>{project.reviewer?.name ?? "Nobody yet"}</dd>
      <dt>Dates</dt>
      <dd>{dateRange(project.start_date, project.end_date)}</dd>
      <dt>Customer contact</dt>
      <dd>{project.contact?.name ?? "None"}</dd>
      <dt>Sites</dt>
      <dd>{project.sites.map((s) => s.name).join(", ") || "—"}</dd>
      <dt>Classification</dt>
      <dd>{project.classification}</dd>
      <dt>Created</dt>
      <dd>{dateTime(project.created_at)}</dd>
      <CustomFieldValues appliesTo="project" values={project.custom} />
    </dl>
  </section>
{/if}

<style>
  .form-wide {
    max-width: 680px;
  }
</style>
