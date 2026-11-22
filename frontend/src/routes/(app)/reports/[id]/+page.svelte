<script lang="ts">
  import { afterNavigate, beforeNavigate, goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import FileText from "@lucide/svelte/icons/file-text";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { branding, pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import AnswerField, { type InReport } from "#lib/components/form/AnswerField.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import PdfPages from "#lib/components/preview/PdfPages.svelte";
  import StylePicker from "#lib/components/preview/StylePicker.svelte";
  import RecordHeader from "#lib/components/RecordHeader.svelte";
  import Checkouts from "#lib/components/reports/Checkouts.svelte";
  import type { ProjectSummary } from "#lib/customers.js";
  import { hourMinute } from "#lib/format.js";
  import { heldByOther, reportsApi, statusOf } from "#lib/reports/api.js";
  import { attempt } from "#lib/reports/attempt.js";
  import { ReportEditor } from "#lib/reports/editor.svelte.js";
  import { PreviewStyle, readsStyles } from "#lib/reportStyles/preview.svelte.js";
  import { session } from "#lib/session.svelte.js";
  import { withStepUp } from "#lib/stepUp.svelte.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { questionsOf, type Question } from "#lib/templates/types.js";
  import { toast } from "#lib/toast.svelte.js";
  import { chooseCustomer } from "#lib/workspace.svelte.js";

  // A report, as its technicians write it and as everyone on its project reads it: the
  // form one step at a time, with the PDF beside it changing as the answers do. It's
  // "Try it" with a real report: the answers are kept on the server, a moment after
  // each change; the rules read the report's own customer, project and people; and a
  // step can be changed only by whoever has it checked out (lib/reports/editor.svelte.ts).
  const id = $derived(Number(page.params.id));
  let editor = $state.raw(new ReportEditor());
  const live = new LivePreview();
  const looks = new PreviewStyle();
  // Technicians and reviewers can't read styles (the server refuses, and logs it), so
  // their preview isn't asked for one: it's drawn in the Skjald default, with none to pick.
  const styled = readsStyles(session.current?.user.capabilities ?? []);
  let here = true;

  onMount(() => {
    if (styled) void looks.load();
  });
  onDestroy(() => {
    here = false;
    live.close();
  });

  // Each report gets an editor of its own, which looks for other people's work while
  // the page is in view. Leaving stops it; a checkout is the holder's to release.
  $effect(() => {
    const wanted = id;
    const opened = untrack(() => {
      const fresh = new ReportEditor();
      editor = fresh;
      shownStep = null;
      renaming = false;
      if (Number.isInteger(wanted) && wanted > 0) void fresh.load(wanted);
      else fresh.loadError = "That report doesn't exist.";
      return fresh;
    });
    const stop = opened.watch();
    return () => {
      stop();
      opened.close();
    };
  });

  const report = $derived(editor.report);
  const content = $derived(editor.content);
  const status = $derived(statusOf(report?.status ?? "draft"));
  const siteName = $derived(report?.site?.name ?? String(report?.context.site?.name ?? ""));

  // The side menu opens on the report's customer and project, with Reports marked.
  const place = $derived(report ? `${report.customer.id}/${report.project.id}/${report.project.archived}` : "");
  $effect(() => {
    if (!place) return;
    const [customer, project] = place.split("/").map(Number);
    untrack(() => {
      api<ProjectSummary>("GET", `/projects/${project}`)
        .then((found) => (here ? chooseCustomer(customer, found) : undefined))
        .catch(() => (here ? chooseCustomer(customer) : undefined));
    });
  });

  $effect(() => {
    if (!report || !content) return;
    live.update({ content, answers: $state.snapshot(editor.answers) as Record<string, unknown>, context: report.context, assets: report.assets,
      library: report.library, timezone: report.time_zone, pageTexts: looks.texts });
  });

  const model = $derived(live.model);
  const hidden = $derived(new Set(model?.formHidden ?? []));
  const required = $derived(new Set(model?.formRequired ?? []));
  const invalid = $derived(new Map((model?.invalid ?? []).map((i) => [i.id, i.message])));
  const steps = $derived((content?.form ?? []).filter((s) => !hidden.has(s.id)));
  // The step shown is kept by ID: a step a rule hides or shows doesn't move the reader to another.
  let shownStep = $state<string | null>(null);
  const step = $derived(steps.find((s) => s.id === shownStep) ?? steps[0]);
  const at = $derived(step ? steps.indexOf(step) : 0);
  const changeable = $derived(step ? editor.mayChange(step.id) : false);
  const holder = $derived(step ? heldByOther(editor.checkouts, step.id) : null);
  const wholeMine = $derived(editor.checkouts.some((c) => c.mine && c.step === null));

  // A question not answered yet shows what it starts as. That isn't saved until the
  // technician changes it; the server reads an unanswered question the same way.
  function answer(q: Question): unknown {
    const kept = editor.answers[q.id];
    return kept === undefined ? model?.defaults[q.id] : kept;
  }

  // A kept secret is shown after a fresh confirmation that it's them. The value goes
  // to the field that asked and nowhere else; the field drops it when its time is up.
  async function reveal(question: string) {
    try {
      return await withStepUp(() => reportsApi.reveal(id, question), "Skjald checks it's really you before it shows a secret. Each look is logged.");
    } catch (e) {
      if (!(e instanceof ApiError && e.reason === "step_up_cancelled") && !sessionGone(e)) {
        toast(e instanceof ApiError ? e.message : "The secret couldn't be shown.", "critical");
      }
      return null;
    }
  }
  const mayReveal = $derived(report?.may_reveal ?? false);
  const inReport = $derived<InReport>({ mayReveal, reveal });

  let busy = $state(false);
  async function run(action: () => Promise<unknown>, otherwise: string): Promise<boolean> {
    busy = true;
    try {
      return await attempt(action, otherwise);
    } finally {
      busy = false;
    }
  }

  // The title and the site are changed in place, by someone holding a checkout.
  let renaming = $state(false);
  let newTitle = $state("");

  async function rename(event: SubmitEvent) {
    event.preventDefault();
    const title = newTitle.trim();
    if (title && (await run(() => editor.update({ title }), "The title couldn't be changed."))) renaming = false;
  }

  function setSite(value: string) {
    void run(() => editor.update({ site_id: value ? Number(value) : null }), "The site couldn't be changed.");
  }

  // What keeps the report from going for review: the server's own list, once the
  // technician asks for it. Someone who only reads the report sees it from the start.
  const questions = $derived(new Map(content ? questionsOf(content).map((q) => [q.id, q]) : []));
  const missing = $derived(editor.verdict?.missing ?? []);
  const listed = $derived(report ? editor.checked || !report.may_edit : false);
  let reviewHeading = $state<HTMLElement>();

  async function check() {
    if (!(await run(() => editor.check(), "The answers couldn't be checked."))) return;
    await tick();
    reviewHeading?.focus();
  }

  let discardOpen = $state(false);
  let discardNumber = $state("");
  let discardError = $state<string | null>(null);

  async function discard(event: SubmitEvent) {
    event.preventDefault();
    if (!report) return;
    const { number, project } = report;
    busy = true;
    discardError = null;
    try {
      await editor.discard(discardNumber);
      discardOpen = false;
      toast(`${number} is discarded.`, "ok");
      await goto(resolve("/(app)/projects/[id]", { id: String(project.id) }));
    } catch (e) {
      if (!sessionGone(e)) discardError = e instanceof ApiError ? e.message : "The report couldn't be discarded.";
    } finally {
      busy = false;
    }
  }

  // Leaving with changes not saved yet: they're saved first, and the reader goes on.
  // Only when that doesn't work are they asked, since leaving would lose them.
  let leaveOpen = $state(false);
  let goOn: (() => void) | null = null;
  let leaving = false;

  beforeNavigate((navigation) => {
    if (leaving || !editor.unsaved) return;
    navigation.cancel();
    // Leaving Skjald, or closing the tab: the browser asks.
    if (navigation.willUnload || !navigation.to) return;
    const to = navigation.to.url;
    const back = navigation.type === "popstate" ? navigation.delta : 0;
    goOn = () => {
      leaving = true;
      if (back) history.go(back);
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- where the reader was going already, as SvelteKit gave it
      else void goto(to);
    };
    void editor.save().catch(() => undefined).then(() => {
      if (editor.unsaved) leaveOpen = true;
      else goOn?.();
    });
  });
  afterNavigate(() => {
    leaving = false;
    leaveOpen = false;
  });
</script>

<svelte:head><title>{pageTitle(report ? `${report.number} ${report.title}` : "Report")}</title></svelte:head>

<svelte:window onbeforeunload={(event) => { if (editor.unsaved) event.preventDefault(); }} />

<main class="page-content report">
  {#if editor.loadError}
    <div>
      <a class="small" href={resolve("/(app)")}>Home</a>
      <p class="alert alert-critical" role="alert">{editor.loadError}</p>
    </div>
  {:else if report && content}
    <a class="back small" href={resolve("/(app)/projects/[id]", { id: String(report.project.id) })}>
      <ChevronLeft size={16} aria-hidden="true" /> {report.project.number} {report.project.name}
    </a>

    <div class="page-header">
      <RecordHeader kind="Report" title={report.title} icon={FileText}>
        <div class="tags">
          <span class="small muted mono">{report.number}</span>
          <Pill tone={status.tone} text={status.label} />
          <span class="small muted">{report.template.name}, version {report.template.version}</span>
          <span class="small muted">
            in <a href={resolve("/(app)/projects/[id]", { id: String(report.project.id) })}>{report.project.name}</a>
            for <a href={resolve("/(app)/customers/[id]", { id: String(report.customer.id) })}>{report.customer.name}</a>
          </span>
          {#if report.may_edit && editor.holding && report.sites.length > 1}
            <label class="site small muted">
              Site
              <select class="input" value={report.site ? String(report.site.id) : ""} disabled={busy} onchange={(e) => setSite(e.currentTarget.value)}>
                <option value="">No site in particular</option>
                {#each report.sites as site (site.id)}<option value={String(site.id)}>{site.name}</option>{/each}
              </select>
            </label>
          {:else if siteName}
            <span class="small muted">Site: {siteName}</span>
          {/if}
          {#if report.may_edit && editor.holding && !renaming}
            <button class="link-button" type="button" onclick={() => { newTitle = report.title; renaming = true; }}>Change the title</button>
          {/if}
        </div>
        {#if renaming}
          <form class="rename" onsubmit={rename}>
            <label class="visually-hidden" for="report-title">Title</label>
            <input id="report-title" class="input" maxlength="200" required bind:value={newTitle} />
            <button class="button button-primary" type="submit" disabled={busy || !newTitle.trim()}>Save the title</button>
            <button class="button button-secondary" type="button" onclick={() => (renaming = false)}>Cancel</button>
          </form>
        {/if}
        {#if report.may_edit}
          <p class="saving small muted" aria-live="polite">
            {#if editor.saveState === "saving"}Saving…
            {:else if editor.saveState === "unsaved"}Not saved yet
            {:else if editor.saveState === "saved" && editor.savedAt}Saved {hourMinute(editor.savedAt)}
            {/if}
          </p>
        {/if}
      </RecordHeader>
      {#if report.may_discard}
        <button class="button button-secondary danger" type="button" disabled={busy}
          onclick={() => { discardNumber = ""; discardError = null; discardOpen = true; }}>
          <Trash2 size={16} aria-hidden="true" />Discard
        </button>
      {/if}
    </div>

    {#if !report.may_edit}
      <p class="alert alert-info">
        {#if report.project.archived}The project is archived, so its reports are read-only.
        {:else if report.status !== "draft"}Only a draft can be changed.
        {:else}You're reading this report. The project's technicians change it.{/if}
      </p>
    {/if}

    {#if editor.saveMessage && (editor.saveState === "refused" || editor.saveState === "failed" || editor.saveState === "lost")}
      <div class="alert alert-critical problem" role="alert">
        <span>{editor.saveState === "lost" ? "" : "Not saved: "}{editor.saveMessage}</span>
        {#if editor.saveState !== "lost"}
          <button class="link-button" type="button" onclick={() => void editor.save()}>Try again</button>
        {/if}
      </div>
    {/if}

    {#if editor.stranded.length}
      {@const one = editor.stranded.length === 1}
      <div class="alert alert-warning problem">
        <span>
          {one ? "An answer you changed isn't saved" : `${editor.stranded.length} answers you changed aren't saved`}, because you don't have
          {one ? "its step" : "their steps"} checked out: {editor.stranded.map((c) => c.question.label || "a question").join(", ")}.
          Check {one ? "the step" : "the steps"} out to save {one ? "it" : "them"}.
        </span>
        <button class="link-button" type="button" onclick={() => editor.drop(editor.stranded.map((c) => c.question))}>
          Drop {one ? "the change" : "the changes"}
        </button>
      </div>
    {/if}

    <Checkouts {editor} steps={content.form} />

    <div class="work">
      <section class="form" aria-labelledby="form-heading">
        <h2 id="form-heading" class="section-title">The form</h2>

        <ol class="progress" aria-label="Steps">
          {#each steps as s, i (s.id)}
            <li><button type="button" aria-current={s.id === step?.id ? "step" : undefined} onclick={() => (shownStep = s.id)}>
              <span class="n">{i + 1}</span> {s.title}
              {#if listed && missing.some((m) => m.step === s.id)}<span class="flag" aria-label="has something to fix">!</span>{/if}
            </button></li>
          {/each}
        </ol>

        {#if step}
          <div class="step">
            <h3 class="step-title">{step.title}</h3>
            {#if step.help}<p class="small muted">{step.help}</p>{/if}
            {#if report.may_edit}
              <div class="hold small">
                {#if changeable}
                  <span>You have {wholeMine ? "the whole report" : "this step"} checked out. What you change is saved as you type.</span>
                {:else if holder}
                  <span>{holder.holder.name} has {holder.step === null ? "the whole report" : "this step"} checked out, so you can read it but not change it.</span>
                {:else}
                  <span>Check this step out to change its answers.</span>
                  <button class="button button-primary" type="button" disabled={busy}
                    onclick={() => run(() => editor.checkOut(step.id), "The step couldn't be checked out.")}>Check out this step</button>
                {/if}
              </div>
            {/if}
            {#each step.questions as q (q.id)}
              {#if !(q.type === "calculated" && !q.settings.show_in_form)}
                <AnswerField question={q} bind:value={() => answer(q), (v) => editor.set(q, v)} required={required.has(q.id)} hidden={hidden.has(q.id)}
                  invalid={invalid.get(q.id) ?? null} computed={q.key ? model?.values[q.key] : undefined} checked={editor.checked} people={report.people}
                  zone={report.time_zone} readonly={!changeable} report={inReport} />
              {/if}
            {:else}
              <p class="small muted">This step has no questions.</p>
            {/each}
          </div>
          <div class="button-row moves">
            <button class="button button-secondary" type="button" disabled={at === 0} onclick={() => (shownStep = steps[at - 1].id)}>Back</button>
            <button class="button button-secondary" type="button" disabled={at >= steps.length - 1} onclick={() => (shownStep = steps[at + 1].id)}>Next</button>
            {#if report.may_edit}
              <button class="button button-primary" type="button" disabled={busy || editor.checking} onclick={check}>Check the answers</button>
            {/if}
          </div>
        {:else}
          <p class="small muted">This report's template has no questions to answer.</p>
        {/if}

        {#if listed}
          <section class="review" aria-labelledby="review-heading">
            <h3 id="review-heading" tabindex="-1" bind:this={reviewHeading}>Before it can go for review</h3>
            {#if missing.length}
              <ul>
                {#each missing as m, i (i)}
                  <li>
                    <button class="link-button" type="button" disabled={!steps.some((s) => s.id === m.step)} onclick={() => (shownStep = m.step)}>
                      {questions.get(m.question)?.label || "A question"}
                    </button>{m.message === "is required." ? " " : ": "}{m.message}
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="small">Nothing missing.</p>
            {/if}
            {#if editor.checked && editor.unsaved}
              <p class="small muted">This is about the answers as they're saved. What isn't saved yet isn't counted.</p>
            {/if}
          </section>
        {/if}
      </section>

      <section class="pdf" aria-labelledby="preview-heading">
        <div class="title-line">
          <h2 id="preview-heading" class="section-title">Preview</h2>
          {#if styled && live.paged}<StylePicker {looks} />{/if}
        </div>
        <p class="small muted note">Drawn in your browser as you type. The signed PDF is made on the server later.</p>
        {#if styled && looks.problem}<p class="alert alert-warning small">{looks.problem}</p>{/if}
        {#if live.problem}<p class="alert alert-warning small">{live.problem}</p>{/if}
        {#if live.paged}
          <PdfPages paged={live.paged} look={looks.look(live.model?.pageTexts, content.settings.made_with_skjald ?? true)} language={content.settings.language}
            reportNumber={report.number} classification={report.project.classification}
            company={String(report.context.company?.name || branding.current.company_name || "")} unsigned />
        {:else if !live.problem}
          <p class="muted">Working out the pages…</p>
        {/if}
      </section>
    </div>
  {/if}
</main>

{#if report?.may_discard}
  <Dialog bind:open={discardOpen} title="Discard {report.number}">
    <form class="stack" onsubmit={discard}>
      {#if discardError}<p class="alert alert-critical" role="alert">{discardError}</p>{/if}
      <p>The draft and its answers are deleted, and its number isn't used again. This can't be undone.</p>
      <div class="field">
        <label for="discard-number">Type the report's number to confirm</label>
        <input id="discard-number" class="input mono" autocomplete="off" spellcheck="false" required bind:value={discardNumber} />
      </div>
      <div class="button-row end">
        <button class="button button-secondary" type="button" onclick={() => (discardOpen = false)}>Cancel</button>
        <button class="button button-primary danger-fill" type="submit" disabled={busy || discardNumber.trim() !== report.number}>Discard for good</button>
      </div>
    </form>
  </Dialog>
{/if}

<Dialog bind:open={leaveOpen} title="Some changes aren't saved">
  <p>{editor.saveMessage ?? "What you changed last couldn't be saved."}</p>
  <p>If you leave now, those changes are lost.</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (leaveOpen = false)}>Stay</button>
    <button class="button button-primary" type="button" onclick={() => goOn?.()}>Leave without saving</button>
  {/snippet}
</Dialog>

<style>
  /* The form and the preview side by side need the room, as the template builder does. */
  .report {
    max-width: none;
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    align-self: flex-start;
    color: var(--text-muted);
    text-decoration: none;
  }
  .back:hover {
    color: var(--link);
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
    margin-top: var(--space-1);
  }
  .site {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  /* Compact, to sit in the line under the title. */
  .site select {
    width: auto;
    min-height: 0;
    height: 34px;
    padding-top: 0;
    padding-bottom: 0;
    font-size: 13px;
  }
  .rename {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .rename .input {
    flex: 1;
    min-width: min(20rem, 100%);
  }
  .saving {
    min-height: 1.4em;
    margin-top: var(--space-1);
  }
  .danger {
    border-color: var(--critical-text);
    color: var(--critical-text);
  }
  .danger-fill {
    background: var(--critical-text);
    color: var(--surface);
  }
  .end {
    justify-content: flex-end;
  }
  .problem {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-1) var(--space-3);
  }
  .problem .link-button {
    color: inherit;
  }
  .work {
    display: grid;
    grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
    gap: var(--space-6);
    align-items: start;
  }
  .form .section-title {
    margin-bottom: var(--space-3);
  }
  .title-line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .note {
    margin: var(--space-1) 0 var(--space-3);
  }
  .progress {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin: 0 0 var(--space-3);
    padding: 0;
    list-style: none;
  }
  .progress button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    background: var(--surface);
    color: var(--text-muted);
    font-size: 13px;
    cursor: pointer;
  }
  .progress button[aria-current="step"] {
    border-color: var(--link);
    color: var(--text);
    font-weight: 600;
  }
  .n {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--surface-subtle);
    font-size: 12px;
  }
  .flag {
    color: var(--critical-text);
    font-weight: 700;
  }
  .step {
    display: grid;
    gap: var(--space-4);
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .step-title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 400;
  }
  .step > p {
    margin: calc(-1 * var(--space-3)) 0 0;
  }
  /* Who holds the step, and the way to take it. */
  .hold {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-4);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  .moves {
    align-items: center;
    margin-top: var(--space-3);
  }
  .moves .button-primary {
    margin-left: auto;
  }
  .review {
    margin-top: var(--space-4);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--surface);
  }
  .review h3 {
    margin: 0 0 var(--space-2);
    font-size: 15px;
  }
  .review ul {
    margin: 0;
    padding-left: var(--space-4);
  }
  .review p + p,
  .review ul + p {
    margin-top: var(--space-2);
  }
  .pdf {
    position: sticky;
    top: var(--space-4);
    max-height: calc(100vh - 2 * var(--space-4));
    overflow-y: auto;
  }
  @media (max-width: 1100px) {
    .work {
      grid-template-columns: minmax(0, 1fr);
    }
    .pdf {
      position: static;
      max-height: none;
    }
  }
</style>
