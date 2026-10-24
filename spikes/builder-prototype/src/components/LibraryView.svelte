<script>
  // The shared library: variables, text snippets and data tables, for every template and report.
  // Technicians may add and change entries; every change is logged, and administrators can lock an entry.
  import {doc, library, session, editLibrary, currentUser, log, KEY_PATTERN} from '../lib/state.svelte.js'

  const KINDS = [
    {id: 'vars', label: 'Variables', prefix: 'vars.', about: 'Single values, such as a phone number or an address. Use them in text as {{vars.name}}.'},
    {id: 'text', label: 'Text snippets', prefix: 'text.', about: 'Reusable paragraphs. Templates print them with {{text.name}}, and technicians can insert them into long answers. A snippet may use variables.'},
    {id: 'tables', label: 'Data tables', prefix: '', about: 'Keys and values, read in rules and calculated values with lookup("table", "key").'},
  ]
  let kind = $state('vars')
  let open = $state({})
  let draft = $state({key: '', value: '', about: ''})
  let addError = $state('')

  const isAdmin = $derived(session.role === 'admin')
  const canEdit = (entry) => !entry.locked || isAdmin
  const info = $derived(KINDS.find((k) => k.id === kind))
  const fmt = (iso) => new Date(iso).toLocaleString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'})

  // Where an entry is used: template text, rules, calculated values and other snippets.
  function usedBy(k, key) {
    const needle = k === 'tables' ? `"${key}"` : `${k}.${key}`
    const texts = [
      ...doc.blocks.flatMap((b) => [b.text, b.title, b.intro, b.caption]),
      ...doc.coverFacts.map((f) => f.text),
      ...doc.computed.map((c) => c.expr),
    ].filter(Boolean)
    const inTemplate = texts.some((t) => t.includes(needle)) || (k === 'tables' && doc.computed.some((c) => c.expr.includes(`lookup(${needle}`)))
    const inSnippets = library.text.filter((t) => t.value.includes(needle)).map((t) => `text.${t.key}`)
    return [...(inTemplate ? ['Security incident report'] : []), ...inSnippets]
  }

  function change(entry, patch, what) {
    if (!canEdit(entry)) return
    editLibrary(kind, entry.key, patch, what)
  }
  function setRow(entry, i, patch) {
    change(entry, {rows: entry.rows.map((r, j) => (j === i ? {...r, ...patch} : r))}, `Changed the row ${patch.key ?? entry.rows[i].key}`)
  }
  function add() {
    const key = draft.key.trim()
    addError = !KEY_PATTERN.test(key) ? 'Use lower-case letters, digits and underscores, starting with a letter.'
      : library[kind].some((e) => e.key === key) ? 'An entry with this name already exists.'
      : kind !== 'tables' && !draft.value.trim() ? 'Give it a value.' : ''
    if (addError) return
    const entry = {key, about: draft.about.trim(), locked: false, history: [{at: new Date().toISOString().slice(0, 16), by: currentUser().name, change: 'Added'}]}
    if (kind === 'tables') entry.rows = [{key: 'key', value: 'value'}]
    else entry.value = draft.value
    library[kind] = [...library[kind], entry]
    log(`Library entry ${info.prefix || 'table '}${key}: Added`)
    draft = {key: '', value: '', about: ''}
  }
</script>

<div class="library">
  <header class="head">
    <h1>Library</h1>
    <p>Values, text snippets and data tables that every template and report can use. Anyone who writes reports can add and change entries. Every change is logged with who and when, administrators can lock an entry, and signed reports keep the values they were signed with.</p>
  </header>

  <div class="tabs" role="tablist" aria-label="Library">
    {#each KINDS as k (k.id)}
      <button type="button" role="tab" aria-selected={kind === k.id} class:active={kind === k.id} onclick={() => (kind = k.id)}>{k.label} <span class="count">{library[k.id].length}</span></button>
    {/each}
  </div>
  <p class="about">{info.about}</p>

  <div class="entries">
    {#each library[kind] as entry (entry.key)}
      {@const uses = usedBy(kind, entry.key)}
      <article class="entry panel" aria-labelledby="e-{entry.key}">
        <div class="entry-head">
          <h2 id="e-{entry.key}" class="mono">{info.prefix}{entry.key}</h2>
          <span class="chips">
            {#if entry.locked}<span class="pill warning">Locked</span>{/if}
            <span class="pill plain">{uses.length ? `Used in ${uses.join(', ')}` : 'Not used yet'}</span>
          </span>
        </div>
        <p class="what">{entry.about || 'No description yet.'}</p>

        {#if kind === 'vars'}
          <label class="sr" for="v-{entry.key}">Value of {entry.key}</label>
          <input id="v-{entry.key}" class="input" value={entry.value} disabled={!canEdit(entry)}
            onchange={(e) => change(entry, {value: e.currentTarget.value}, `Changed the value to “${e.currentTarget.value}”`)} />
        {:else if kind === 'text'}
          <label class="sr" for="v-{entry.key}">Text of {entry.key}</label>
          <textarea id="v-{entry.key}" class="input" rows="3" value={entry.value} disabled={!canEdit(entry)}
            onchange={(e) => change(entry, {value: e.currentTarget.value}, 'Changed the text')}></textarea>
        {:else}
          <div class="rows">
            <div class="row head-row" aria-hidden="true"><span>Key</span><span>Value</span></div>
            {#each entry.rows as row, i (i)}
              <div class="row">
                <input class="input mono" aria-label="Key, row {i + 1}" value={row.key} disabled={!canEdit(entry)} onchange={(e) => setRow(entry, i, {key: e.currentTarget.value.trim()})} />
                <input class="input" aria-label="Value, row {i + 1}" value={row.value} disabled={!canEdit(entry)} onchange={(e) => setRow(entry, i, {value: e.currentTarget.value})} />
              </div>
            {/each}
            {#if canEdit(entry)}<button type="button" class="btn add" onclick={() => change(entry, {rows: [...entry.rows, {key: `key_${entry.rows.length + 1}`, value: ''}]}, 'Added a row')}>Add a row</button>{/if}
          </div>
        {/if}

        <div class="entry-foot">
          {#if entry.locked && !isAdmin}<span class="muted">Only an administrator can change a locked entry.</span>{/if}
          {#if isAdmin}
            <button type="button" class="btn quiet" onclick={() => editLibrary(kind, entry.key, {locked: !entry.locked}, entry.locked ? 'Unlocked' : 'Locked')}>{entry.locked ? 'Unlock' : 'Lock'}</button>
          {/if}
          <button type="button" class="btn quiet" aria-expanded={!!open[entry.key]} onclick={() => (open[entry.key] = !open[entry.key])}>History ({entry.history.length})</button>
        </div>
        {#if open[entry.key]}
          <ol class="history">
            {#each [...entry.history].reverse() as h, i (i)}<li><span class="mono">{fmt(h.at)}</span> {h.by}: {h.change}</li>{/each}
          </ol>
        {/if}
      </article>
    {/each}
  </div>

  <form class="panel add-form" onsubmit={(e) => { e.preventDefault(); add() }}>
    <div class="panel-head"><h2>Add {kind === 'vars' ? 'a variable' : kind === 'text' ? 'a text snippet' : 'a data table'}</h2></div>
    <div class="panel-body">
      <div class="field"><label for="new-key">Name</label>
        <div class="key-row">{#if info.prefix}<span class="mono muted">{info.prefix}</span>{/if}<input id="new-key" class="input mono" bind:value={draft.key} placeholder="service_window" /></div></div>
      {#if kind !== 'tables'}
        <div class="field"><label for="new-value">{kind === 'text' ? 'Text' : 'Value'}</label>
          {#if kind === 'text'}<textarea id="new-value" class="input" rows="3" bind:value={draft.value}></textarea>{:else}<input id="new-value" class="input" bind:value={draft.value} />{/if}</div>
      {/if}
      <div class="field"><label for="new-about">What it is</label><input id="new-about" class="input" bind:value={draft.about} /></div>
      {#if addError}<span class="error" role="alert">{addError}</span>{/if}
      <button type="submit" class="btn primary">Add</button>
    </div>
  </form>
</div>

<style>
  .library { display: grid; gap: 14px; max-width: 980px; }
  .head { display: grid; gap: 4px; }
  h1 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 26px; }
  .head p { margin: 0; color: var(--text-muted); max-width: 78ch; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px; border-radius: var(--radius-md); background: var(--surface-subtle); justify-self: start; }
  .tabs button { min-height: 36px; padding: 0 14px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); font-weight: 600; font-size: 13px; cursor: pointer; }
  .tabs button.active { background: var(--surface); color: var(--text); box-shadow: 0 0 0 1px var(--border); }
  .count { font-weight: 500; color: var(--text-muted); }
  .about { margin: 0; font-size: 13px; color: var(--text-muted); max-width: 78ch; }
  .entries { display: grid; gap: 10px; }
  .entry { display: grid; gap: 8px; padding: 14px 16px; }
  .entry-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; }
  .entry-head h2 { margin: 0; font-size: 14px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chips .pill { white-space: normal; }
  .what { margin: 0; font-size: 13px; color: var(--text-muted); }
  .rows { display: grid; gap: 4px; }
  .row { display: grid; grid-template-columns: minmax(0, 0.7fr) minmax(0, 1.3fr); gap: 4px; }
  .head-row span { font-size: 11.5px; font-weight: 600; color: var(--text-muted); }
  .add { justify-self: start; }
  .entry-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 6px; }
  .entry-foot .muted { margin-right: auto; }
  .muted { color: var(--text-muted); font-size: 12.5px; }
  .history { margin: 0; padding: 8px 12px 8px 30px; border-radius: var(--radius-md); background: var(--surface-subtle); font-size: 12.5px; display: grid; gap: 2px; }
  .key-row { display: flex; align-items: center; gap: 6px; }
  .add-form .btn { justify-self: start; }
  .error { font-size: 12.5px; color: var(--critical-text); }
  .input:disabled { opacity: 1; color: var(--text-muted); background: var(--surface-subtle); }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
