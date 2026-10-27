<script lang="ts">
  import Where from "#lib/components/builder/Where.svelte";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import type { Settings, TemplateContent } from "#lib/templates/types.js";

  // The template's settings panel: who signs, whether review is required, how reports
  // are numbered, how they may be delivered, and which styles they may use.
  const draft = useDraft();
  const settings = $derived((draft.content as TemplateContent).settings);
  const prefixOk = $derived(/^[A-Z]{2,6}$/.test(settings.prefix));

  function toggle<K extends "delivery" | "styles">(key: K, value: Settings[K][number], on: boolean) {
    const list = settings[key] as string[];
    const next = on ? [...new Set([...list, value])] : list.filter((v) => v !== value);
    if (next.length) (settings[key] as string[]) = next;
  }

  const year = new Date().getFullYear();
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This is version {draft.shownVersion}. Choose Edit to change it in a new draft.</p>
{/if}

<fieldset class="settings" disabled={draft.readonly}>
  <section class="section">
    <h2 class="section-title">Numbering <Where pdf /></h2>
    <div class="field narrow">
      <label for="prefix">Report number prefix</label>
      <input id="prefix" class="input mono" value={settings.prefix} maxlength="6" aria-invalid={prefixOk ? undefined : "true"}
        oninput={(e) => (settings.prefix = e.currentTarget.value.toUpperCase().replace(/[^A-Z]/g, ""))} />
      <span class="hint" class:error={!prefixOk}>
        {prefixOk ? `Reports are numbered ${settings.prefix}-${year}-0001, ${settings.prefix}-${year}-0002 and so on. Templates with the same prefix share the count.` : "Two to six capital letters, such as INC."}
      </span>
    </div>
    <div class="field narrow">
      <label for="language">Language for dates and numbers</label>
      <select id="language" class="input" bind:value={settings.language}>
        <option value="en">English: 21 October 2026, 1,234.5</option>
        <option value="da">Danish: 21. oktober 2026, 1.234,5</option>
      </select>
      <span class="hint">How format_date() and format_number() write. The template's own words are as you write them; copy it to translate.</span>
    </div>
  </section>

  <section class="section">
    <h2 class="section-title">Review and signing <Where pdf /></h2>
    <fieldset class="choices">
      <legend>Review</legend>
      <label class="check"><input type="radio" name="review" value="mandatory" bind:group={settings.review} /> Required: a reviewer approves each report before it's signed</label>
      <label class="check"><input type="radio" name="review" value="optional" bind:group={settings.review} /> Optional: a report can go straight from draft to signing</label>
    </fieldset>
    <fieldset class="choices">
      <legend>Who signs</legend>
      <label class="check"><input type="radio" name="signing" value="technician" bind:group={settings.signing} /> The technician</label>
      <label class="check"><input type="radio" name="signing" value="technician_reviewer" bind:group={settings.signing} /> The technician, then the reviewer</label>
      <label class="check"><input type="radio" name="signing" value="company" bind:group={settings.signing} /> The company seal</label>
    </fieldset>
    <p class="small muted">The Signatures block on the Layout tab sets how each signature looks on the page.</p>
  </section>

  <section class="section">
    <h2 class="section-title">Delivery <Where builder /></h2>
    <fieldset class="choices">
      <legend>The technician may deliver reports as</legend>
      <label class="check"><input type="checkbox" checked={settings.delivery.includes("download")} onchange={(e) => toggle("delivery", "download", e.currentTarget.checked)} /> A download</label>
      <label class="check"><input type="checkbox" checked={settings.delivery.includes("email")} onchange={(e) => toggle("delivery", "email", e.currentTarget.checked)} /> An email attachment</label>
      <label class="check"><input type="checkbox" checked={settings.delivery.includes("protected_pdf")} onchange={(e) => toggle("delivery", "protected_pdf", e.currentTarget.checked)} /> A password-protected PDF</label>
      <label class="check muted"><input type="checkbox" disabled /> A secure link with an access code <span class="small">(release 1.1)</span></label>
    </fieldset>
  </section>

  <section class="section">
    <h2 class="section-title">Look <Where pdf /></h2>
    <fieldset class="choices">
      <legend>Styles reports may use</legend>
      <label class="check"><input type="checkbox" checked={settings.styles.includes("company")} onchange={(e) => toggle("styles", "company", e.currentTarget.checked)} /> The company brand</label>
      <label class="check"><input type="checkbox" checked={settings.styles.includes("customer")} onchange={(e) => toggle("styles", "customer", e.currentTarget.checked)} /> The customer's own style, where it has one</label>
    </fieldset>
    <label class="check"><input type="checkbox" bind:checked={settings.customer_background} /> Print on the customer's report background, where it has one</label>
    <p class="small muted">A customer without a background gets plain pages.</p>
  </section>
</fieldset>

<style>
  .settings {
    display: grid;
    gap: var(--space-2);
    max-width: 760px;
    margin: var(--space-4) 0 0;
    padding: 0;
    border: 0;
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .narrow {
    max-width: 420px;
  }
  .choices {
    display: grid;
    gap: var(--space-1);
    margin: 0 0 var(--space-3);
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-1);
    font-size: 14px;
    font-weight: 600;
  }
  .error {
    color: var(--critical-text);
  }
</style>
