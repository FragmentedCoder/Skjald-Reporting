<script lang="ts">
  import Archive from "@lucide/svelte/icons/archive";
  import ArchiveRestore from "@lucide/svelte/icons/archive-restore";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import { onMount } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import RowMenu, { type MenuItem } from "#lib/components/RowMenu.svelte";
  import { CUSTOM_TYPES, customFieldsApi, type AppliesTo, type CustomField, type CustomFieldType } from "#lib/customFields.js";
  import { keyFrom } from "#lib/templates/edit.js";
  import { toast } from "#lib/toast.svelte.js";

  // Custom fields: what the company keeps about customers and projects beyond the
  // built-in details. Managers fill them in; templates read them by name.
  const KINDS: { kind: AppliesTo; label: string; about: string }[] = [
    { kind: "customer", label: "Customers", about: "Filled in on the customer's settings, and read as customer.custom.name." },
    { kind: "project", label: "Projects", about: "Filled in with the project's details, and read as project.custom.name." },
  ];

  let fields = $state<CustomField[] | null>(null);
  let error = $state<string | null>(null);
  let showArchived = $state(false);

  async function load() {
    try {
      fields = await customFieldsApi.list(true);
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The custom fields could not be loaded.";
    }
  }
  onMount(load);

  const listed = (kind: AppliesTo) => (fields ?? []).filter((f) => f.applies_to === kind && (showArchived || !f.archived));
  const typeLabel = (type: CustomFieldType) => CUSTOM_TYPES.find((t) => t.type === type)?.label ?? type;

  // Adding one, or changing one
  let editing = $state(false);
  let current = $state<CustomField | null>(null);
  let appliesTo = $state<AppliesTo>("customer");
  let label = $state("");
  let key = $state("");
  let keyTouched = $state(false);
  let type = $state<CustomFieldType>("text");
  let help = $state("");
  let options = $state("");
  let busy = $state(false);

  function open(field: CustomField | null, kind: AppliesTo = "customer") {
    current = field;
    appliesTo = field?.applies_to ?? kind;
    label = field?.label ?? "";
    key = field?.key ?? "";
    keyTouched = !!field;
    type = field?.type ?? "text";
    help = field?.help ?? "";
    options = field?.options.join("\n") ?? "";
    editing = true;
  }

  $effect(() => {
    if (!keyTouched && !current) key = keyFrom(label);
  });

  const optionList = $derived(options.split("\n").map((o) => o.trim()).filter(Boolean));

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      if (current) {
        await customFieldsApi.update(current.id, { label, help, options: optionList, position: current.position, archived: current.archived });
        toast(`${label} is saved.`, "ok");
      } else {
        await customFieldsApi.create({ applies_to: appliesTo, key, label, type, help, options: optionList });
        toast(`${label} is added: templates read it as ${appliesTo}.custom.${key}.`, "ok");
      }
      editing = false;
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The field couldn't be saved.", "critical");
    } finally {
      busy = false;
    }
  }

  async function change(field: CustomField, patch: Partial<Pick<CustomField, "position" | "archived">>, done: string) {
    try {
      await customFieldsApi.update(field.id, { label: field.label, help: field.help, options: field.options, position: field.position, archived: field.archived, ...patch });
      toast(done, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "That didn't work. Try again.", "critical");
    }
  }

  // Moving swaps places with the neighbour, numbering the list afresh.
  async function move(field: CustomField, by: -1 | 1) {
    const list = listed(field.applies_to).filter((f) => !f.archived);
    const at = list.findIndex((f) => f.id === field.id);
    const other = list[at + by];
    if (!other) return;
    const order = list.map((f) => f.id);
    [order[at], order[at + by]] = [order[at + by], order[at]];
    try {
      for (const [i, id] of order.entries()) {
        const f = list.find((x) => x.id === id) as CustomField;
        if (f.position !== i) await customFieldsApi.update(f.id, { label: f.label, help: f.help, options: f.options, position: i, archived: f.archived });
      }
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "That didn't work. Try again.", "critical");
    }
  }

  function menu(field: CustomField, index: number, count: number): MenuItem[] {
    if (field.archived) return [{ label: "Restore", icon: ArchiveRestore, run: () => void change(field, { archived: false }, `${field.label} is back on the forms.`) }];
    const items: MenuItem[] = [{ label: "Change", icon: Pencil, run: () => open(field) }];
    if (index > 0) items.push({ label: "Move up", icon: ArrowUp, run: () => void move(field, -1) });
    if (index < count - 1) items.push({ label: "Move down", icon: ArrowDown, run: () => void move(field, 1) });
    items.push({ label: "Archive", icon: Archive, run: () => void change(field, { archived: true }, `${field.label} is archived: it's off the forms, and the values filled in are kept.`) });
    return items;
  }
</script>

<svelte:head><title>{pageTitle("Custom fields")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Custom fields</h1>
      <p class="small muted">What the company keeps about customers and projects beyond the built-in details, such as a support agreement or a ticket number. The values are encrypted with each customer's own key.</p>
    </div>
    <button class="button button-primary" type="button" onclick={() => open(null)}><Plus size={18} aria-hidden="true" /> Add a field</button>
  </div>
  <label class="check small"><input type="checkbox" bind:checked={showArchived} /> Show archived fields</label>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if fields}
    {#each KINDS as k (k.kind)}
      {@const rows = listed(k.kind)}
      {@const active = rows.filter((f) => !f.archived)}
      <section class="section" aria-labelledby="{k.kind}-title">
        <h2 class="section-title" id="{k.kind}-title">{k.label}</h2>
        <p class="small muted">{k.about}</p>
        {#if rows.length}
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Field</th><th>Templates read it as</th><th>Type</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {#each rows as field (field.id)}
                  <tr>
                    <td>{field.label} {#if field.archived}<Pill text="Archived" />{/if}
                      {#if field.help}<span class="small muted block">{field.help}</span>{/if}</td>
                    <td class="mono small">{field.applies_to}.custom.{field.key}</td>
                    <td class="small">{typeLabel(field.type)}{field.type === "dropdown" ? `: ${field.options.join(", ")}` : ""}</td>
                    <td class="actions"><RowMenu label="Actions for {field.label}" items={menu(field, active.indexOf(field), active.length)} /></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="small">None yet.</p>
        {/if}
        <div><button class="button button-secondary small" type="button" onclick={() => open(null, k.kind)}><Plus size={16} aria-hidden="true" /> Add a field for {k.label.toLowerCase()}</button></div>
      </section>
    {/each}
  {:else if !error}
    <p class="muted">Loading…</p>
  {/if}
</main>

<Dialog bind:open={editing} title={current ? `Change ${current.label}` : "Add a field"}>
  <form id="custom-field" class="stack" onsubmit={save}>
    {#if !current}
      <fieldset class="field">
        <legend>For</legend>
        <label class="check"><input type="radio" name="applies-to" value="customer" bind:group={appliesTo} /> Customers</label>
        <label class="check"><input type="radio" name="applies-to" value="project" bind:group={appliesTo} /> Projects</label>
      </fieldset>
    {/if}
    <div class="field">
      <label for="field-label">Label</label>
      <input id="field-label" class="input" bind:value={label} required maxlength="100" />
    </div>
    {#if !current}
      <div class="field">
        <label for="field-key">Name in templates</label>
        <input id="field-key" class="input mono" bind:value={key} oninput={() => (keyTouched = true)} required maxlength="50" pattern="[a-z][a-z0-9_]*" />
        <span class="hint">Templates read it as {appliesTo}.custom.{key || "name"}. It can't change once the field is made.</span>
      </div>
      <div class="field">
        <label for="field-type">Type</label>
        <select id="field-type" class="input" bind:value={type}>
          {#each CUSTOM_TYPES as t (t.type)}<option value={t.type}>{t.label}</option>{/each}
        </select>
      </div>
    {/if}
    {#if (current?.type ?? type) === "dropdown"}
      <div class="field">
        <label for="field-options">Options</label>
        <textarea id="field-options" class="input" rows="4" bind:value={options} required></textarea>
        <span class="hint">One a line.</span>
      </div>
    {/if}
    <div class="field">
      <label for="field-help">Help <span class="muted">(optional)</span></label>
      <input id="field-help" class="input" bind:value={help} maxlength="300" />
      <span class="hint">Shown under the field on the form.</span>
    </div>
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (editing = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="custom-field" disabled={busy}>{current ? "Save" : "Add the field"}</button>
  {/snippet}
</Dialog>

<style>
  .check {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-2);
    font-weight: 500;
  }
  .block {
    display: block;
  }
  .actions {
    width: 1%;
    white-space: nowrap;
  }
</style>
