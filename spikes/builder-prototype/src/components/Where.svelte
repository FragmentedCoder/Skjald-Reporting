<script>
  // Says who sees a thing: the technician in the form, the customer in the PDF, or only the template's builders.
  let {form = false, pdf = false, builder = false, compact = false} = $props()
</script>

<span class="where" class:compact>
  {#if form}<span class="tag form" title="The technician sees this while filling in the report"><span aria-hidden="true">✎</span>Form</span>{/if}
  {#if pdf}<span class="tag pdf" title="Printed in the PDF the customer receives"><span aria-hidden="true">▤</span>PDF</span>{/if}
  {#if builder}<span class="tag builder" title="Only administrators and report designers see this"><span aria-hidden="true">⚙</span>Builder only</span>{/if}
</span>

<style>
  .where { display: inline-flex; flex-wrap: wrap; gap: 4px; }
  .tag { display: inline-flex; align-items: center; gap: 4px; padding: 0 7px; min-height: 20px; border-radius: 6px;
    font-size: 11px; font-weight: 600; line-height: 1.2; white-space: nowrap; border: 1px solid; }
  .tag span { font-size: 10.5px; }
  .form { color: var(--info-text); border-color: var(--info-text); }
  .pdf { color: var(--text); border-color: var(--border-strong); }
  .builder { color: var(--text-muted); border-color: var(--border); border-style: dashed; }
  .compact .tag { min-height: 18px; padding: 0 5px; font-size: 10.5px; }
</style>
