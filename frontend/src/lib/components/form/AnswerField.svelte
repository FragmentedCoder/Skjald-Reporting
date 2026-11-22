<script lang="ts" module>
  /** What a question needs from the report it's answered in. */
  export interface InReport {
    /** Whether this person may see a kept secret: those who write or review the report. */
    mayReveal: boolean;
    /**
     * Asks the server for a kept secret, which takes a fresh confirmation that it's
     * them. Null when it isn't shown; whoever gives this says why.
     */
    reveal: (question: string) => Promise<{ value: string; seconds: number } | null>;
  }
</script>

<script lang="ts">
  import { onDestroy, tick, untrack } from "svelte";
  import Eye from "@lucide/svelte/icons/eye";
  import EyeOff from "@lucide/svelte/icons/eye-off";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { formatDate, instantOf, wallAt } from "#lib/cel/dates.js";
  import { LOCALES } from "#lib/cel/library.js";
  import RichTextEditor from "#lib/components/builder/RichTextEditor.svelte";
  import RichView from "#lib/components/preview/RichView.svelte";
  import { cvssScore } from "#lib/templates/answers.js";
  import { answerProblem, cellProblem } from "#lib/templates/formChecks.js";
  import { keepPhoto } from "#lib/templates/localPhotos.js";
  import { COLUMN_TYPES, settingsOf } from "#lib/templates/fields.js";
  import { peopleFor, type Person } from "#lib/templates/preview.js";
  import { DOTS, maskedSecret } from "#lib/templates/secrets.js";
  import { NAME_MAX, sign, signed } from "#lib/templates/signature.js";
  import type { Question, RichText } from "#lib/templates/types.js";

  // One question as the technician answers it, with its own check as they type. In
  // "Try it", files and photos stay in the browser and a secret is the sample's own.
  // In a report, a kept secret is never here: only that it's filled in, until someone
  // who may asks to see it for a moment.
  let { question, value = $bindable(), required, hidden, invalid, computed, checked = false, people = [], zone, readonly = false, report = null }: {
    question: Question;
    value: unknown;
    required: boolean;
    hidden: boolean;
    /** The answers have been checked: a required question left empty says so, visited or not. */
    checked?: boolean;
    /** The question's own rule saying the answer isn't valid. */
    invalid: string | null;
    /** A calculated value, worked out. */
    computed: unknown;
    /** The people a person question can pick. */
    people?: Person[];
    /** The company's time zone, which dates are typed in. */
    zone: string;
    /** Shown to be read, not changed: a report's step someone else holds, or nobody does. */
    readonly?: boolean;
    /** The report the question is answered in; none in "Try it". */
    report?: InReport | null;
  } = $props();

  const s = $derived(settingsOf(question.type, question.settings));
  const id = $derived(`a-${question.id}`);
  let touched = $state(false);
  let showSecret = $state(false);

  type Column = { key: string; label: string; type: string; required?: boolean; settings?: Record<string, unknown> };
  type Option = { value: string; label: string };
  const options = $derived((s.options ?? []) as Option[]);
  const columns = $derived((s.columns ?? []) as Column[]);
  const rows = $derived(Array.isArray(value) ? (value as Record<string, unknown>[]) : []);

  // A signature question is signed by a name typed and a box ticked to confirm it
  // (templates/signature.ts). Only a confirmed name is an answer: until the box is
  // ticked, the name being typed is kept here.
  const signature = $derived(question.type === "signature" ? signed(value) : null);
  let typedName = $state("");
  const signerName = $derived(signature?.name ?? typedName);

  function typeName(text: string) {
    typedName = text;
    // A confirmation belongs to the name it was given for: another name isn't confirmed.
    if (signature) value = null;
  }

  function confirmName(box: HTMLInputElement) {
    const answer = box.checked ? sign(signerName) : null;
    // The name stays in its field either way: in the answer once it's confirmed.
    typedName = answer ? "" : signerName;
    value = answer;
    box.checked = answer !== null;
  }

  // A report's kept secret arrives masked (templates/secrets.ts). It's shown as filled
  // in; "Replace" gives an empty field, and what's typed there is the answer, sent like
  // any other. The field stays while it's being typed in, though the save a moment
  // later brings the answer back masked; once it's left, what was typed is forgotten here.
  const kept = $derived(report && question.type === "secret" ? maskedSecret(value) : null);
  let secretDraft = $state<string | null>(null);
  let secretInput = $state<HTMLInputElement>();

  function typeSecret(text: string) {
    if (report) secretDraft = text;
    value = text;
  }

  async function replace() {
    hide();
    showSecret = false;
    secretDraft = "";
    await tick();
    secretInput?.focus();
  }

  function leaveSecret() {
    secretDraft = null;
    showSecret = false;
  }

  // A kept secret shown on request: here only, for the seconds the server gives, then
  // forgotten. Sooner when the page is put away, the field goes, or another secret is kept.
  let revealed = $state<string | null>(null);
  let revealLeft = $state(0);
  let revealing = $state(false);
  let revealTimer: ReturnType<typeof setInterval> | undefined;
  let here = true;

  function hide() {
    clearInterval(revealTimer);
    revealed = null;
    revealLeft = 0;
  }

  async function reveal() {
    if (!report || revealing) return;
    revealing = true;
    try {
      const shown = await report.reveal(question.id);
      if (!shown || !kept || !here) return;
      const until = Date.now() + shown.seconds * 1000;
      revealed = shown.value;
      revealLeft = shown.seconds;
      clearInterval(revealTimer);
      revealTimer = setInterval(() => {
        revealLeft = Math.ceil((until - Date.now()) / 1000);
        if (revealLeft <= 0) hide();
      }, 500);
    } finally {
      revealing = false;
    }
  }

  onDestroy(() => {
    here = false;
    hide();
  });

  // What's kept changed (saved, replaced by someone, cleared): a value shown belongs to
  // the secret kept before, and a typed one that's saved and no longer in use is dropped.
  const keptAs = $derived(kept ? kept.printed : null);
  $effect(() => {
    const now = keptAs;
    untrack(() => {
      hide();
      // Still in its field (or on the button beside it): it stays until that's left.
      if (now !== null && secretDraft !== null && !secretInput?.parentElement?.contains(document.activeElement)) leaveSecret();
    });
  });

  const empty = $derived(value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)
    || (question.type === "cvss" && !(value as { vector?: string } | null)?.vector) || (question.type === "signature" && !signature));
  // The answer's own problem. A list's are said in its cells; under the list only once
  // the answers are checked (too few rows, say, isn't a mistake while rows are being added).
  const listed = $derived(question.type === "repeating" || question.type === "table");
  const typeProblem = $derived(listed && !checked ? null : answerProblem(question, value));
  const problem = $derived(typeProblem ?? invalid ?? ((touched || checked) && required && empty ? "This is required." : null));

  // Dates are typed in the company's time zone and kept as an instant.
  function toInput(iso: unknown, date: boolean): string {
    if (typeof iso !== "string" || !iso) return "";
    const w = wallAt(new Date(iso).getTime(), zone);
    const pad = (n: number) => String(n).padStart(2, "0");
    // Four digits for the year, as the field writes it: a year half typed (0002 on
    // the way to 2026) then comes back as it was typed, and the typing isn't disturbed.
    const day = `${String(w.year).padStart(4, "0")}-${pad(w.month)}-${pad(w.day)}`;
    return date ? day : `${day}T${pad(w.hour)}:${pad(w.minute)}`;
  }
  function fromInput(text: string): string | null {
    const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/.exec(text);
    if (!match) return null;
    const [, y, mo, d, h, mi] = match.map(Number);
    return new Date(instantOf({ year: y, month: mo, day: d, hour: h || 0, minute: mi || 0, second: 0 }, zone)).toISOString();
  }

  function setCvss(vector: string) {
    const scored = cvssScore(vector.trim());
    value = { vector: vector.trim(), score: scored?.score ?? 0, severity: scored?.severity ?? "" };
  }

  function addRow() {
    value = [...rows, Object.fromEntries(columns.map((c) => [c.key, c.type === "yes_no" ? false : null]))];
  }

  /** One cell of a repeating group, or of a table with a fixed number of rows. */
  function setGridCell(fixedRows: number | null, index: number, key: string, cell: unknown) {
    const base = fixedRows === null ? rows : Array.from({ length: fixedRows }, (_, i) => rows[i] ?? {});
    value = base.map((row, i) => (i === index ? { ...row, [key]: cell } : row));
  }

  function files(event: Event) {
    const list = (event.currentTarget as HTMLInputElement).files;
    if (!list?.length) return;
    const chosen = Array.from(list).map((f) => (question.type === "photo" ? keepPhoto(f) : f.name));
    value = s.multiple ? [...(Array.isArray(value) ? value : []), ...chosen].slice(0, Number(s.max_photos ?? s.max_files ?? 10)) : chosen.slice(0, 1);
  }

  const cell = (type: string, current: unknown, set: (v: unknown) => void, label: string, settings?: Record<string, unknown>) => ({ type, current, set, label, settings });
</script>

{#snippet input(c: ReturnType<typeof cell>)}
  {#if c.type === "number"}
    <input class="input" type="number" step={c.settings?.whole ? "1" : "any"} aria-label={c.label} value={c.current ?? ""} disabled={readonly}
      oninput={(e) => c.set(e.currentTarget.value === "" ? null : Number(e.currentTarget.value))} />
  {:else if c.type === "yes_no"}
    <input type="checkbox" aria-label={c.label} checked={Boolean(c.current)} disabled={readonly} onchange={(e) => c.set(e.currentTarget.checked)} />
  {:else if c.type === "dropdown"}
    <select class="input" aria-label={c.label} value={String(c.current ?? "")} disabled={readonly} onchange={(e) => c.set(e.currentTarget.value || null)}>
      <option value="">Choose…</option>
      {#each (c.settings?.options ?? []) as Option[] as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
    </select>
  {:else if c.type === "datetime"}
    {@const day = c.settings?.mode === "date"}
    <input class="input" type={day ? "date" : "datetime-local"} aria-label={c.label} value={toInput(c.current, day)} disabled={readonly} oninput={(e) => c.set(fromInput(e.currentTarget.value))} />
  {:else}
    <input class="input" aria-label={c.label} value={String(c.current ?? "")} disabled={readonly} oninput={(e) => c.set(e.currentTarget.value)} />
  {/if}
{/snippet}

<svelte:document onvisibilitychange={() => { if (document.hidden) hide(); }} />

{#if !hidden}
  {#if question.type === "heading"}
    <h3 class="part">{question.label}</h3>
    {#if question.help}<p class="small muted">{question.help}</p>{/if}
  {:else}
    <div class="answer" class:problem={problem}>
      <div class="question">
        <span class="label" id="{id}-label">{question.label}{#if required}<span class="required" aria-label="required"> *</span>{/if}</span>
        {#if question.help}<span class="small muted" id="{id}-help">{question.help}</span>{/if}
      </div>
      <!-- Left, not moved about in: a signature's name isn't missing its tick while the box is being reached. -->
      <div class="control" role="group" aria-labelledby="{id}-label"
        onfocusout={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) touched = true; }}>
        {#if question.type === "rich_text" && readonly}
          <!-- Read, the text is drawn as the PDF draws it: from its nodes, never as HTML. -->
          {@const doc = value && typeof value === "object" ? (value as RichText) : null}
          <div class="read-text">{#if doc?.content?.length}<RichView nodes={doc.content} />{:else}<span class="muted">—</span>{/if}</div>
        {:else if question.type === "rich_text"}
          <RichTextEditor bind:value={() => (value as RichText | null) ?? null, (v) => (value = v)} entries={[]} names={false} label={question.label} id={id} />
        {:else if question.type === "number"}
          <span class="with-unit">
            <input class="input" type="number" step={s.whole ? "1" : "any"} aria-labelledby="{id}-label" value={value ?? ""} disabled={readonly}
              oninput={(e) => (value = e.currentTarget.value === "" ? null : Number(e.currentTarget.value))} />
            {#if s.unit}<span class="muted">{s.unit}</span>{/if}
          </span>
        {:else if question.type === "datetime"}
          <input class="input" type={s.mode === "date" ? "date" : "datetime-local"} aria-labelledby="{id}-label" disabled={readonly}
            value={toInput(value, s.mode === "date")} oninput={(e) => (value = fromInput(e.currentTarget.value))} />
        {:else if question.type === "yes_no"}
          <span class="choices">
            <label class="check"><input type="radio" name={id} checked={value === true} disabled={readonly} onchange={() => (value = true)} /> {s.yes_label}</label>
            <label class="check"><input type="radio" name={id} checked={value === false} disabled={readonly} onchange={() => (value = false)} /> {s.no_label}</label>
          </span>
        {:else if question.type === "dropdown"}
          <select class="input" aria-labelledby="{id}-label" value={String(value ?? "")} disabled={readonly} onchange={(e) => (value = e.currentTarget.value || null)}>
            <option value="">Choose…</option>
            {#each options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
          </select>
        {:else if question.type === "person"}
          {@const choices = peopleFor(question, people)}
          {@const picked = (value as Person | null)?.id ?? ""}
          <select class="input" aria-labelledby="{id}-label" value={picked} disabled={readonly}
            onchange={(e) => (value = choices.find((p) => p.id === e.currentTarget.value) ?? null)}>
            <option value="">Choose…</option>
            {#each choices as p (p.id)}<option value={p.id}>{p.display_name}{p.job_title ? `, ${p.job_title}` : ""}</option>{/each}
            {#if picked && !choices.some((p) => p.id === picked)}<option value={picked}>{(value as Person).display_name}</option>{/if}
          </select>
        {:else if question.type === "multi_select"}
          <span class="choices">
            {#each options as o (o.value)}
              <label class="check"><input type="checkbox" checked={Array.isArray(value) && value.includes(o.value)} disabled={readonly}
                onchange={(e) => (value = e.currentTarget.checked ? [...(Array.isArray(value) ? value : []), o.value] : (Array.isArray(value) ? value : []).filter((v) => v !== o.value))} /> {o.label}</label>
            {/each}
          </span>
        {:else if question.type === "cvss"}
          {@const scored = value as { vector?: string; score?: number; severity?: string } | null}
          <input class="input mono" aria-labelledby="{id}-label" placeholder="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
            value={scored?.vector ?? ""} disabled={readonly} oninput={(e) => setCvss(e.currentTarget.value)} spellcheck="false" />
          {#if scored?.vector && !typeProblem}<span class="small">Score {scored.score} · {scored.severity}</span>{/if}
        {:else if question.type === "secret" && kept && secretDraft === null}
          <span class="kept">
            <span class="mono" aria-hidden="true">{DOTS}{DOTS}</span>
            <span class="small">Filled in. Its value isn't shown.</span>
          </span>
          {#if revealed !== null}
            <input class="input mono" readonly value={revealed} aria-label="{question.label}, shown for a moment" autocomplete="off" spellcheck="false" />
            <span class="small muted">
              Hidden again in {revealLeft} second{revealLeft === 1 ? "" : "s"}.
              <button class="link-button" type="button" onclick={hide}>Hide it now</button>
            </span>
          {/if}
          {#if (report?.mayReveal && revealed === null) || !readonly}
            <span class="secret-actions">
              {#if report?.mayReveal && revealed === null}
                <button class="link-button" type="button" disabled={revealing} onclick={reveal}>Show for 30 seconds</button>
              {/if}
              {#if !readonly}<button class="link-button" type="button" onclick={replace}>Replace</button>{/if}
            </span>
          {/if}
          <span class="small muted">
            {report?.mayReveal ? "Seeing it takes a confirmation that it's you, and each look is logged." : "Only those who write or review this report can see it."}
          </span>
        {:else if question.type === "secret"}
          <!-- Left, a typed secret that's kept by now gives way to "Filled in". -->
          <span class="with-unit" onfocusout={(e) => { if (kept && !e.currentTarget.contains(e.relatedTarget as Node | null)) leaveSecret(); }}>
            <input bind:this={secretInput} class="input mono" type={showSecret ? "text" : "password"} aria-labelledby="{id}-label" autocomplete="off" disabled={readonly}
              value={report ? (secretDraft ?? (typeof value === "string" ? value : "")) : String(value ?? "")} oninput={(e) => typeSecret(e.currentTarget.value)} />
            <button class="icon" type="button" aria-label={showSecret ? "Hide it" : "Show it"} disabled={readonly} onclick={() => (showSecret = !showSecret)}>
              {#if showSecret}<EyeOff size={16} aria-hidden="true" />{:else}<Eye size={16} aria-hidden="true" />{/if}
            </button>
          </span>
          <span class="small muted">
            {#if kept && secretDraft === ""}Type the new one. Left empty, the one that's there is kept.
            {:else if report}Kept encrypted. Seeing it again takes a confirmation that it's you, and each look is logged.
            {:else}In a report, seeing it again takes a confirmation with multifactor, and each look is logged.{/if}
          </span>
        {:else if (question.type === "photo" || question.type === "file") && report}
          <input type="file" aria-labelledby="{id}-label" disabled />
          <span class="small muted">Files and photos can't be added yet: they come with the next part of Phase 3.</span>
        {:else if question.type === "photo" || question.type === "file"}
          <input type="file" aria-labelledby="{id}-label" accept={question.type === "photo" ? "image/png,image/jpeg" : undefined} multiple={Boolean(s.multiple)} onchange={files} />
          {#if Array.isArray(value) && value.length}
            <span class="small">{value.length} {question.type === "photo" ? "photo" : "file"}{value.length === 1 ? "" : "s"} <button class="link-button" type="button" onclick={() => (value = [])}>Remove</button></span>
          {/if}
          <span class="small muted">Here they stay in your browser. In a report they're uploaded, scanned and encrypted{question.type === "photo" ? ", and their location data removed" : ""}.</span>
        {:else if question.type === "signature"}
          <label class="small" for="{id}-name">Full name</label>
          <input class="input" id="{id}-name" maxlength={NAME_MAX} autocomplete="off" spellcheck="false" value={signerName} disabled={readonly}
            oninput={(e) => typeName(e.currentTarget.value)} aria-invalid={problem ? "true" : undefined} />
          <label class="check"><input type="checkbox" checked={signature !== null} disabled={readonly || !signerName.trim()} aria-describedby="{id}-signing"
            onchange={(e) => confirmName(e.currentTarget)} /> I confirm this is my signature</label>
          <span class="small muted" id="{id}-signing">
            {signature
              ? `Confirmed ${formatDate(signature.at, "d MMMM yyyy, HH:mm", zone, LOCALES.en)}.${readonly ? "" : " Changing the name takes the confirmation back."}`
              : readonly ? "Not signed." : "Type the name, then tick the box to sign."}
          </span>
        {:else if question.type === "repeating" || question.type === "table"}
          {@const fixed = question.type === "table" ? ((s.rows ?? []) as { key: string; label: string }[]) : null}
          <div class="grid-wrap">
            <table class="grid">
              <thead><tr>{#if fixed}<th></th>{/if}{#each columns as c (c.key)}<th>{c.label}{c.type === "number" && c.settings?.unit ? ` (${c.settings.unit})` : ""}</th>{/each}{#if !fixed && !readonly}<th><span class="visually-hidden">Remove</span></th>{/if}</tr></thead>
              <tbody>
                {#each fixed ?? rows as row, r (r)}
                  <tr>
                    {#if fixed}<th scope="row">{(row as { label: string }).label}</th>{/if}
                    {#each columns as c (c.key)}
                      {@const current = (rows[r] ?? {})[c.key]}
                      {@const message = current === null || current === undefined || current === "" ? (checked ? cellProblem(c, current) : null) : cellProblem(c, current)}
                      <td class:bad={message}>
                        {@render input(cell(COLUMN_TYPES.includes(c.type) ? c.type : "text", current, (v) => setGridCell(fixed?.length ?? null, r, c.key, v),
                          `${c.label}, row ${r + 1}`, settingsOf(c.type, c.settings ?? {})))}
                        {#if message}<span class="small cell-problem">{message}</span>{/if}
                      </td>
                    {/each}
                    {#if !fixed && !readonly}<td><button class="icon" type="button" aria-label="Remove row {r + 1}" onclick={() => (value = rows.filter((_, i) => i !== r))}><X size={14} aria-hidden="true" /></button></td>{/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          {#if !fixed && !readonly && rows.length < Number(s.max_rows ?? 100)}
            <button class="link-button small add" type="button" onclick={addRow}><Plus size={14} aria-hidden="true" /> Add a row</button>
          {:else if !fixed && readonly && !rows.length}
            <span class="small muted">No rows.</span>
          {/if}
        {:else if question.type === "calculated"}
          <output class="computed" aria-labelledby="{id}-label">{computed === null || computed === undefined || computed === "" ? "—" : computed instanceof Date ? computed.toISOString().slice(0, 16).replace("T", " ") : String(computed)}</output>
        {:else}
          <input class="input" class:mono={["ip", "mac", "serial", "hostname"].includes(question.type)} aria-labelledby="{id}-label"
            placeholder={readonly ? "" : String(s.placeholder ?? "")} value={String(value ?? "")} disabled={readonly} oninput={(e) => (value = e.currentTarget.value)}
            spellcheck={question.type === "text"} aria-invalid={problem ? "true" : undefined} />
          {#if question.type === "barcode" && !report}<span class="small muted">In a report, it's read from a photo of the code.</span>
          {:else if question.type === "barcode" && !readonly}<span class="small muted">Type what the code says. Reading it from a photo comes with files and photos.</span>{/if}
        {/if}
        {#if problem}<span class="small message" role="status">{problem}</span>{/if}
      </div>
    </div>
  {/if}
{/if}

<style>
  .part {
    margin: var(--space-4) 0 0;
    font-family: var(--font-display);
    font-size: 19px;
    font-weight: 400;
  }
  .answer {
    display: grid;
    gap: var(--space-1);
  }
  .question {
    display: grid;
  }
  .label {
    font-weight: 600;
  }
  .required {
    color: var(--critical-text);
  }
  .control {
    display: grid;
    gap: var(--space-1);
  }
  .with-unit {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .with-unit .input {
    flex: 1;
    min-width: 0;
  }
  .choices {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
  }
  .kept {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-2);
  }
  .secret-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
  }
  .icon {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text-muted);
    cursor: pointer;
  }
  .grid-wrap {
    overflow-x: auto;
  }
  .grid {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  .grid th {
    padding: var(--space-1);
    text-align: left;
    font-weight: 600;
  }
  .grid td {
    padding: 2px;
    vertical-align: top;
  }
  .grid td.bad :global(.input) {
    border-color: var(--critical-text);
  }
  .cell-problem {
    display: block;
    color: var(--critical-text);
  }
  .add {
    justify-self: start;
  }
  .computed {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
  }
  /* Read, not changed: set back a little, and as easy to read as the rest. */
  .answer :global(.input:disabled) {
    background: var(--surface-subtle);
    color: var(--text);
    opacity: 1;
    cursor: not-allowed;
  }
  .read-text {
    display: grid;
    gap: var(--space-2);
    min-height: 44px;
    padding: 10px 12px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
    overflow-wrap: anywhere;
  }
  .problem .input,
  .problem :global(.input[aria-invalid]) {
    border-color: var(--critical-text);
  }
  .message {
    color: var(--critical-text);
  }
</style>
