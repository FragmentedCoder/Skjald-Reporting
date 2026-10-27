<script lang="ts">
  import { settingsOf } from "#lib/templates/fields.js";
  import type { Question } from "#lib/templates/types.js";
  import ColumnsEditor from "./ColumnsEditor.svelte";
  import OptionsEditor from "./OptionsEditor.svelte";

  // A question's own settings, by field type (backend/app/templates/fields.py says
  // what each one takes).
  let { question }: { question: Question } = $props();

  // Settings the server hasn't filled in yet get their defaults first.
  $effect.pre(() => {
    const filled = settingsOf(question.type, question.settings);
    if (Object.keys(filled).some((k) => !(k in question.settings))) question.settings = filled;
  });

  const s = $derived(question.settings as Record<string, never>);
  const id = $derived(`q-${question.id}`);

  type Option = { value: string; label: string };
  type Column = { key: string; label: string; type: string; required: boolean; settings: Record<string, unknown> };
  type Row = { key: string; label: string };

  const rows = $derived((s.rows ?? []) as Row[]);

  const num = (value: string) => (value === "" ? null : Number(value));
  const toggle = (list: string[], value: string, on: boolean) => (on ? [...new Set([...list, value])] : list.filter((v) => v !== value));
</script>

{#snippet pattern()}
  <div class="field">
    <label for="{id}-pattern">Must match <span class="muted">(optional)</span></label>
    <input id="{id}-pattern" class="input mono" value={s.pattern ?? ""} maxlength="500" spellcheck="false"
      oninput={(e) => (question.settings.pattern = e.currentTarget.value || null)} placeholder="^[A-Z]{"{2}"}-[0-9]+$" />
    <span class="hint">A regular expression in RE2 syntax, checked as the technician types.</span>
  </div>
  {#if s.pattern}
    <div class="field">
      <label for="{id}-pattern-message">Message when it doesn't</label>
      <input id="{id}-pattern-message" class="input" bind:value={question.settings.pattern_message} maxlength="300" />
    </div>
  {/if}
{/snippet}

{#if question.type === "text"}
  <div class="field">
    <label for="{id}-max">Longest answer, in characters</label>
    <input id="{id}-max" class="input narrow" type="number" min="1" max="10000" value={s.max_length}
      oninput={(e) => (question.settings.max_length = num(e.currentTarget.value) ?? 500)} />
  </div>
  {@render pattern()}
  <div class="field">
    <label for="{id}-placeholder">Example shown in the empty field <span class="muted">(optional)</span></label>
    <input id="{id}-placeholder" class="input" bind:value={question.settings.placeholder} maxlength="200" />
  </div>
{:else if question.type === "rich_text"}
  <div class="field">
    <label for="{id}-max">Longest answer, in characters</label>
    <input id="{id}-max" class="input narrow" type="number" min="1" max="100000" value={s.max_length}
      oninput={(e) => (question.settings.max_length = num(e.currentTarget.value) ?? 20000)} />
  </div>
  <label class="check"><input type="checkbox" bind:checked={() => Boolean(question.settings.snippets), (v) => (question.settings.snippets = v)} /> The technician can insert text snippets from the library</label>
{:else if question.type === "number"}
  <label class="check"><input type="checkbox" bind:checked={() => Boolean(question.settings.whole), (v) => (question.settings.whole = v)} /> Whole numbers only</label>
  <div class="row">
    <div class="field">
      <label for="{id}-min">Smallest</label>
      <input id="{id}-min" class="input" type="number" step="any" value={s.min ?? ""} oninput={(e) => (question.settings.min = num(e.currentTarget.value))} />
    </div>
    <div class="field">
      <label for="{id}-maxn">Largest</label>
      <input id="{id}-maxn" class="input" type="number" step="any" value={s.max ?? ""} oninput={(e) => (question.settings.max = num(e.currentTarget.value))} />
    </div>
  </div>
  <div class="row">
    {#if !s.whole}
      <div class="field">
        <label for="{id}-decimals">Decimals shown</label>
        <input id="{id}-decimals" class="input" type="number" min="0" max="6" value={s.decimals}
          oninput={(e) => (question.settings.decimals = num(e.currentTarget.value) ?? 1)} />
      </div>
    {/if}
    <div class="field">
      <label for="{id}-unit">Unit <span class="muted">(optional)</span></label>
      <input id="{id}-unit" class="input" bind:value={question.settings.unit} maxlength="20" placeholder="GB" />
    </div>
  </div>
{:else if question.type === "datetime"}
  <div class="field">
    <label for="{id}-mode">Asks for</label>
    <select id="{id}-mode" class="input" bind:value={question.settings.mode}>
      <option value="datetime">A date and a time</option>
      <option value="date">A date</option>
    </select>
  </div>
{:else if question.type === "yes_no"}
  <div class="row">
    <div class="field"><label for="{id}-yes">Yes is shown as</label><input id="{id}-yes" class="input" bind:value={question.settings.yes_label} maxlength="50" /></div>
    <div class="field"><label for="{id}-no">No is shown as</label><input id="{id}-no" class="input" bind:value={question.settings.no_label} maxlength="50" /></div>
  </div>
{:else if question.type === "dropdown" || question.type === "multi_select"}
  <OptionsEditor bind:options={() => s.options as Option[], (v) => (question.settings.options = v)} {id} />
  {#if question.type === "multi_select"}
    <div class="row">
      <div class="field"><label for="{id}-fewest">Fewest choices</label>
        <input id="{id}-fewest" class="input" type="number" min="0" value={s.min_selected ?? ""} oninput={(e) => (question.settings.min_selected = num(e.currentTarget.value))} /></div>
      <div class="field"><label for="{id}-most">Most choices</label>
        <input id="{id}-most" class="input" type="number" min="1" value={s.max_selected ?? ""} oninput={(e) => (question.settings.max_selected = num(e.currentTarget.value))} /></div>
    </div>
  {/if}
{:else if question.type === "ip"}
  <div class="row">
    <div class="field">
      <label for="{id}-versions">Takes</label>
      <select id="{id}-versions" class="input" bind:value={question.settings.versions}>
        <option value="any">IPv4 or IPv6</option><option value="v4">IPv4 only</option><option value="v6">IPv6 only</option>
      </select>
    </div>
    <div class="field">
      <label for="{id}-cidr">A prefix such as /24</label>
      <select id="{id}-cidr" class="input" bind:value={question.settings.cidr}>
        <option value="no">Not allowed</option><option value="allowed">Allowed</option><option value="required">Required</option>
      </select>
    </div>
  </div>
{:else if question.type === "serial"}
  {@render pattern()}
{:else if question.type === "cvss"}
  <fieldset class="plain">
    <legend>Versions the technician can use</legend>
    {#each ["3.1", "4.0"] as version (version)}
      <label class="check"><input type="checkbox" checked={(s.versions as string[]).includes(version)}
        disabled={(s.versions as string[]).length === 1 && (s.versions as string[]).includes(version)}
        onchange={(e) => (question.settings.versions = toggle(s.versions, version, e.currentTarget.checked))} /> CVSS {version}</label>
    {/each}
  </fieldset>
  <p class="small muted">Rules read the score, the vector and the severity: answers.{question.key}.score, .vector and .severity.</p>
{:else if question.type === "secret"}
  <div class="field">
    <label for="{id}-pdf">In the PDF</label>
    <select id="{id}-pdf" class="input" bind:value={question.settings.pdf}>
      <option value="partial">Printed partly, as Hu••••••in</option>
      <option value="omit">Not printed</option>
    </select>
    <span class="hint">At most a quarter of the characters, three at each end, with a run of dots that hides the length. Technicians see the whole secret after confirming it's them; every look is logged. Rules see only whether it's filled in.</span>
  </div>
{:else if question.type === "photo" || question.type === "file"}
  {@const most = question.type === "photo" ? "max_photos" : "max_files"}
  <label class="check"><input type="checkbox" bind:checked={() => Boolean(question.settings.multiple), (v) => (question.settings.multiple = v)} /> The technician can add several</label>
  {#if s.multiple}
    <div class="field">
      <label for="{id}-most">At most</label>
      <input id="{id}-most" class="input narrow" type="number" min="1" max="50" value={s[most]}
        oninput={(e) => (question.settings[most] = num(e.currentTarget.value) ?? 10)} />
    </div>
  {/if}
  {#if question.type === "photo"}<p class="small muted">Location and other data are removed from photos when they're uploaded.</p>{/if}
{:else if question.type === "barcode"}
  <fieldset class="plain">
    <legend>Codes to read</legend>
    {#each [["qr", "QR code"], ["code128", "Code 128"], ["ean13", "EAN-13"], ["datamatrix", "Data Matrix"]] as [value, label] (value)}
      <label class="check"><input type="checkbox" checked={(s.formats as string[]).includes(value)}
        disabled={(s.formats as string[]).length === 1 && (s.formats as string[]).includes(value)}
        onchange={(e) => (question.settings.formats = toggle(s.formats, value, e.currentTarget.checked))} /> {label}</label>
    {/each}
  </fieldset>
{:else if question.type === "repeating"}
  <ColumnsEditor bind:columns={() => s.columns as Column[], (v) => (question.settings.columns = v)} {id} />
  <div class="row">
    <div class="field"><label for="{id}-fewest-rows">Fewest rows</label>
      <input id="{id}-fewest-rows" class="input" type="number" min="0" max="500" value={s.min_rows} oninput={(e) => (question.settings.min_rows = num(e.currentTarget.value) ?? 0)} /></div>
    <div class="field"><label for="{id}-most-rows">Most rows</label>
      <input id="{id}-most-rows" class="input" type="number" min="1" max="500" value={s.max_rows} oninput={(e) => (question.settings.max_rows = num(e.currentTarget.value) ?? 100)} /></div>
  </div>
{:else if question.type === "table"}
  <fieldset class="plain rows">
    <legend>Rows</legend>
    {#each rows as row, index (index)}
      <div class="row-line">
        <input class="input" aria-label="Row {index + 1}" bind:value={row.label} maxlength="200" />
        <input class="input mono" aria-label="Row {index + 1} variable name" bind:value={row.key} maxlength="50" />
        <button class="button button-secondary" type="button" disabled={(s.rows as Row[]).length === 1}
          onclick={() => (question.settings.rows = (s.rows as Row[]).filter((_, i) => i !== index))}>Remove</button>
      </div>
    {/each}
    <button class="button button-secondary" type="button"
      onclick={() => (question.settings.rows = [...(s.rows as Row[]), { key: `row_${(s.rows as Row[]).length + 1}`, label: `Row ${(s.rows as Row[]).length + 1}` }])}>Add a row</button>
  </fieldset>
  <ColumnsEditor bind:columns={() => s.columns as Column[], (v) => (question.settings.columns = v)} {id} />
{:else if question.type === "calculated"}
  <div class="field">
    <label for="{id}-result">Gives</label>
    <select id="{id}-result" class="input" bind:value={question.settings.result}>
      <option value="text">Text</option><option value="number">A decimal number</option><option value="whole">A whole number</option>
      <option value="yes_no">Yes or no</option><option value="date">A date and time</option>
    </select>
  </div>
  <label class="check"><input type="checkbox" bind:checked={() => Boolean(question.settings.show_in_form), (v) => (question.settings.show_in_form = v)} /> Show it in the form, so the technician sees it</label>
{:else if question.type !== "heading"}
  <p class="small muted">Nothing else to set: Skjald checks the answer is a valid {question.type === "hostname" ? "host name" : question.type === "mac" ? "MAC address" : question.type === "email" ? "email address" : question.type === "phone" ? "phone number" : "value"}.</p>
{/if}

<style>
  .row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: var(--space-2);
  }
  .narrow {
    max-width: 140px;
  }
  .plain {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding: 0;
    border: 0;
  }
  .plain legend {
    margin-bottom: var(--space-1);
    font-size: 14px;
    font-weight: 600;
  }
  .row-line {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 0.8fr) auto;
    gap: var(--space-2);
  }
  .rows > .button {
    justify-self: start;
  }
</style>
