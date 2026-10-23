<script>
  // Visual "show only when" rule. Stored as a small object; shown and evaluated as CEL.
  import {OPERATORS, toCelExpression} from '../lib/cel.js'
  import {doc, templateData, ruleResult} from '../lib/state.svelte.js'

  let {rule, onchange, idPrefix} = $props()

  const usable = $derived(doc.questions.filter((q) => ['yesno', 'number', 'text', 'dropdown', 'ip', 'longtext'].includes(q.type)))
  const question = $derived(rule ? doc.questions.find((q) => q.key === rule.field) : null)
  const ops = $derived(Object.entries(OPERATORS).filter(([, o]) => !question || o.types.includes(question.type)))
  const expr = $derived(rule ? toCelExpression(rule, doc.questions) : '')
  const result = $derived(rule ? ruleResult(rule, templateData(doc.answers)) : null)

  function enable(on) {
    if (!on) return onchange(null)
    const first = usable.find((q) => q.type === 'yesno') ?? usable[0]
    onchange({field: first.key, op: 'is', value: first.type === 'yesno' ? true : ''})
  }
  function setField(key) {
    const q = doc.questions.find((x) => x.key === key)
    const op = OPERATORS[rule.op].types.includes(q.type) ? rule.op : 'is'
    onchange({field: key, op, value: q.type === 'yesno' ? true : q.type === 'number' ? 0 : ''})
  }
</script>

<div class="cond">
  <label class="check"><input id="{idPrefix}-cond-on" type="checkbox" checked={!!rule} onchange={(e) => enable(e.currentTarget.checked)} />
    Show only when a rule is true</label>

  {#if rule}
    <div class="row">
      <div class="field">
        <label for="{idPrefix}-cond-field">Question</label>
        <select id="{idPrefix}-cond-field" class="input" value={rule.field} onchange={(e) => setField(e.currentTarget.value)}>
          {#each usable as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
        </select>
      </div>
      <div class="field">
        <label for="{idPrefix}-cond-op">Condition</label>
        <select id="{idPrefix}-cond-op" class="input" value={rule.op} onchange={(e) => onchange({...rule, op: e.currentTarget.value})}>
          {#each ops as [key, op] (key)}<option value={key}>{op.label}</option>{/each}
        </select>
      </div>
      <div class="field">
        <label for="{idPrefix}-cond-value">Value</label>
        {#if question?.type === 'yesno'}
          <select id="{idPrefix}-cond-value" class="input" value={rule.value ? 'yes' : 'no'}
            onchange={(e) => onchange({...rule, value: e.currentTarget.value === 'yes'})}>
            <option value="yes">Yes</option><option value="no">No</option>
          </select>
        {:else if question?.type === 'dropdown' && rule.op !== 'matches'}
          <select id="{idPrefix}-cond-value" class="input" value={rule.value} onchange={(e) => onchange({...rule, value: e.currentTarget.value})}>
            {#each question.options as o (o)}<option value={o}>{o}</option>{/each}
          </select>
        {:else}
          <input id="{idPrefix}-cond-value" class="input" type={question?.type === 'number' ? 'number' : 'text'} step="0.1"
            value={rule.value} oninput={(e) => onchange({...rule, value: question?.type === 'number' ? Number(e.currentTarget.value) : e.currentTarget.value})} />
        {/if}
      </div>
    </div>
    <div class="cel">
      <span class="overline">Stored as CEL</span>
      <code class="mono">{expr}</code>
      {#if result && !result.ok}
        <span class="pill critical">Error: {result.error}</span>
      {:else if result}
        <span class="pill {result.value ? 'ok' : 'plain'}">{result.value ? 'Shown' : 'Hidden'} with the sample answers</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .cond { display: grid; gap: 10px; }
  .row { display: grid; gap: 8px; }
  .cel { display: grid; gap: 6px; justify-items: start; padding: 10px 12px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  code { display: block; max-width: 100%; overflow-x: auto; white-space: pre; color: var(--text); }
</style>
