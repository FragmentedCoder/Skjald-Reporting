<script lang="ts">
  import Eye from "@lucide/svelte/icons/eye";
  import EyeOff from "@lucide/svelte/icons/eye-off";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { instantOf, wallAt } from "#lib/cel/dates.js";
  import RichTextEditor from "#lib/components/builder/RichTextEditor.svelte";
  import { checkAnswer, cvssScore } from "#lib/templates/answers.js";
  import { COLUMN_TYPES, settingsOf } from "#lib/templates/fields.js";
  import type { Question, RichText } from "#lib/templates/types.js";
  import SignaturePad from "./SignaturePad.svelte";

  // One question as the technician answers it, with its own check as they type. Files,
  // photos and signatures stay in the browser here: uploading them is the report's job.
  let { question, value = $bindable(), required, hidden, invalid, computed, zone = "Europe/Copenhagen" }: {
    question: Question;
    value: unknown;
    required: boolean;
    hidden: boolean;
    /** The question's own rule saying the answer isn't valid. */
    invalid: string | null;
    /** A calculated value, worked out. */
    computed: unknown;
    zone?: string;
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

  const empty = $derived(value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)
    || (question.type === "cvss" && !(value as { vector?: string } | null)?.vector));
  const typeProblem = $derived.by(() => {
    if (question.type === "cvss") return checkAnswer("cvss", s, (value as { vector?: string } | null)?.vector ?? "");
    if (question.type === "multi_select" && Array.isArray(value)) {
      const n = value.length;
      if (s.min_selected !== null && n < Number(s.min_selected)) return `Choose at least ${s.min_selected}.`;
      if (s.max_selected !== null && n > Number(s.max_selected)) return `Choose at most ${s.max_selected}.`;
    }
    return checkAnswer(question.type, s, value);
  });
  const problem = $derived(typeProblem ?? invalid ?? (touched && required && empty ? "This is required." : null));

  // Dates are typed in the company's time zone and kept as an instant.
  function toInput(iso: unknown, date: boolean): string {
    if (typeof iso !== "string" || !iso) return "";
    const w = wallAt(new Date(iso).getTime(), zone);
    const pad = (n: number) => String(n).padStart(2, "0");
    const day = `${w.year}-${pad(w.month)}-${pad(w.day)}`;
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
    const chosen = Array.from(list).map((f) => (question.type === "photo" ? URL.createObjectURL(f) : f.name));
    value = s.multiple ? [...(Array.isArray(value) ? value : []), ...chosen].slice(0, Number(s.max_photos ?? s.max_files ?? 10)) : chosen.slice(0, 1);
  }

  const cell = (type: string, current: unknown, set: (v: unknown) => void, label: string, settings?: Record<string, unknown>) => ({ type, current, set, label, settings });
</script>

{#snippet input(c: ReturnType<typeof cell>)}
  {#if c.type === "number"}
    <input class="input" type="number" step={c.settings?.whole ? "1" : "any"} aria-label={c.label} value={c.current ?? ""}
      oninput={(e) => c.set(e.currentTarget.value === "" ? null : Number(e.currentTarget.value))} />
  {:else if c.type === "yes_no"}
    <input type="checkbox" aria-label={c.label} checked={Boolean(c.current)} onchange={(e) => c.set(e.currentTarget.checked)} />
  {:else if c.type === "dropdown"}
    <select class="input" aria-label={c.label} value={String(c.current ?? "")} onchange={(e) => c.set(e.currentTarget.value || null)}>
      <option value="">Choose…</option>
      {#each (c.settings?.options ?? []) as Option[] as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
    </select>
  {:else if c.type === "datetime"}
    <input class="input" type="datetime-local" aria-label={c.label} value={toInput(c.current, false)} oninput={(e) => c.set(fromInput(e.currentTarget.value))} />
  {:else}
    <input class="input" aria-label={c.label} value={String(c.current ?? "")} oninput={(e) => c.set(e.currentTarget.value)} />
  {/if}
{/snippet}

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
      <div class="control" role="group" aria-labelledby="{id}-label" onfocusout={() => (touched = true)}>
        {#if question.type === "rich_text"}
          <RichTextEditor bind:value={() => (value as RichText | null) ?? null, (v) => (value = v)} entries={[]} names={false} label={question.label} id={id} />
        {:else if question.type === "number"}
          <span class="with-unit">
            <input class="input" type="number" step={s.whole ? "1" : "any"} aria-labelledby="{id}-label" value={value ?? ""}
              oninput={(e) => (value = e.currentTarget.value === "" ? null : Number(e.currentTarget.value))} />
            {#if s.unit}<span class="muted">{s.unit}</span>{/if}
          </span>
        {:else if question.type === "datetime"}
          <input class="input" type={s.mode === "date" ? "date" : "datetime-local"} aria-labelledby="{id}-label"
            value={toInput(value, s.mode === "date")} oninput={(e) => (value = fromInput(e.currentTarget.value))} />
        {:else if question.type === "yes_no"}
          <span class="choices">
            <label class="check"><input type="radio" name={id} checked={value === true} onchange={() => (value = true)} /> {s.yes_label}</label>
            <label class="check"><input type="radio" name={id} checked={value === false} onchange={() => (value = false)} /> {s.no_label}</label>
          </span>
        {:else if question.type === "dropdown"}
          <select class="input" aria-labelledby="{id}-label" value={String(value ?? "")} onchange={(e) => (value = e.currentTarget.value || null)}>
            <option value="">Choose…</option>
            {#each options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
          </select>
        {:else if question.type === "multi_select"}
          <span class="choices">
            {#each options as o (o.value)}
              <label class="check"><input type="checkbox" checked={Array.isArray(value) && value.includes(o.value)}
                onchange={(e) => (value = e.currentTarget.checked ? [...(Array.isArray(value) ? value : []), o.value] : (Array.isArray(value) ? value : []).filter((v) => v !== o.value))} /> {o.label}</label>
            {/each}
          </span>
        {:else if question.type === "cvss"}
          {@const scored = value as { vector?: string; score?: number; severity?: string } | null}
          <input class="input mono" aria-labelledby="{id}-label" placeholder="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
            value={scored?.vector ?? ""} oninput={(e) => setCvss(e.currentTarget.value)} spellcheck="false" />
          {#if scored?.vector && !typeProblem}<span class="small">Score {scored.score} · {scored.severity}</span>{/if}
        {:else if question.type === "secret"}
          <span class="with-unit">
            <input class="input mono" type={showSecret ? "text" : "password"} aria-labelledby="{id}-label" autocomplete="off"
              value={String(value ?? "")} oninput={(e) => (value = e.currentTarget.value)} />
            <button class="icon" type="button" aria-label={showSecret ? "Hide it" : "Show it"} onclick={() => (showSecret = !showSecret)}>
              {#if showSecret}<EyeOff size={16} aria-hidden="true" />{:else}<Eye size={16} aria-hidden="true" />{/if}
            </button>
          </span>
          <span class="small muted">In a report, seeing it again takes a confirmation with multifactor, and each look is logged.</span>
        {:else if question.type === "photo" || question.type === "file"}
          <input type="file" aria-labelledby="{id}-label" accept={question.type === "photo" ? "image/png,image/jpeg" : undefined} multiple={Boolean(s.multiple)} onchange={files} />
          {#if Array.isArray(value) && value.length}
            <span class="small">{value.length} {question.type === "photo" ? "photo" : "file"}{value.length === 1 ? "" : "s"} <button class="link-button" type="button" onclick={() => (value = [])}>Remove</button></span>
          {/if}
          <span class="small muted">Here they stay in your browser. In a report they're uploaded, scanned and encrypted{question.type === "photo" ? ", and their location data removed" : ""}.</span>
        {:else if question.type === "signature"}
          <SignaturePad bind:value={() => (value as string | null) ?? null, (v) => (value = v)} label={question.label} />
        {:else if question.type === "repeating" || question.type === "table"}
          {@const fixed = question.type === "table" ? ((s.rows ?? []) as { key: string; label: string }[]) : null}
          <div class="grid-wrap">
            <table class="grid">
              <thead><tr>{#if fixed}<th></th>{/if}{#each columns as c (c.key)}<th>{c.label}</th>{/each}{#if !fixed}<th><span class="visually-hidden">Remove</span></th>{/if}</tr></thead>
              <tbody>
                {#each fixed ?? rows as row, r (r)}
                  <tr>
                    {#if fixed}<th scope="row">{(row as { label: string }).label}</th>{/if}
                    {#each columns as c (c.key)}
                      {@const current = (rows[r] ?? {})[c.key]}
                      {@const message = checkAnswer(c.type, settingsOf(c.type, c.settings ?? {}), current)}
                      <td class:bad={message}>
                        {@render input(cell(COLUMN_TYPES.includes(c.type) ? c.type : "text", current, (v) => setGridCell(fixed?.length ?? null, r, c.key, v),
                          `${c.label}, row ${r + 1}`, settingsOf(c.type, c.settings ?? {})))}
                        {#if message}<span class="small cell-problem">{message}</span>{/if}
                      </td>
                    {/each}
                    {#if !fixed}<td><button class="icon" type="button" aria-label="Remove row {r + 1}" onclick={() => (value = rows.filter((_, i) => i !== r))}><X size={14} aria-hidden="true" /></button></td>{/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          {#if !fixed && rows.length < Number(s.max_rows ?? 100)}
            <button class="link-button small add" type="button" onclick={addRow}><Plus size={14} aria-hidden="true" /> Add a row</button>
          {/if}
        {:else if question.type === "calculated"}
          <output class="computed" aria-labelledby="{id}-label">{computed === null || computed === undefined || computed === "" ? "—" : computed instanceof Date ? computed.toISOString().slice(0, 16).replace("T", " ") : String(computed)}</output>
        {:else}
          <input class="input" class:mono={["ip", "mac", "serial", "hostname"].includes(question.type)} aria-labelledby="{id}-label"
            placeholder={String(s.placeholder ?? "")} value={String(value ?? "")} oninput={(e) => (value = e.currentTarget.value)}
            spellcheck={question.type === "text"} aria-invalid={problem ? "true" : undefined} />
          {#if question.type === "barcode"}<span class="small muted">In a report, it's read from a photo of the code.</span>{/if}
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
  .problem .input,
  .problem :global(.input[aria-invalid]) {
    border-color: var(--critical-text);
  }
  .message {
    color: var(--critical-text);
  }
</style>
