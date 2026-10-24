<script>
  import Mark from './components/Mark.svelte'
  import BuilderView from './components/builder/BuilderView.svelte'
  import ReportView from './components/report/ReportView.svelte'
  import LibraryView from './components/LibraryView.svelte'
  import CheckView from './components/CheckView.svelte'
  import {USERS} from './lib/sample.js'
  import {session, canBuild} from './lib/state.svelte.js'

  const BUILDER_VIEWS = ['questions', 'layout', 'data', 'try']
  const VIEWS = [...BUILDER_VIEWS, 'report', 'library', 'check']
  let lastBuilderView = 'layout'

  const nav = $derived([
    {id: 'report', label: 'Reports', active: session.view === 'report'},
    ...(canBuild() ? [{id: lastBuilderView, label: 'Templates', active: BUILDER_VIEWS.includes(session.view)}] : []),
    {id: 'library', label: 'Library', active: session.view === 'library'},
    {id: 'check', label: 'Check a report', active: session.view === 'check'},
  ])

  // A bare #token opens a screen, so each one can be linked.
  function fromHash() {
    const token = location.hash.slice(1)
    return VIEWS.includes(token) ? token : null
  }
  function show(view) {
    if (BUILDER_VIEWS.includes(view)) {
      if (!canBuild()) view = 'report'
      else lastBuilderView = view
    }
    session.view = view
    try { history.replaceState(null, '', `#${view}`) } catch { /* not allowed in some frames */ }
  }
  show(fromHash() ?? session.view)

  function setRole(role) {
    session.role = role
    if (BUILDER_VIEWS.includes(session.view) && !canBuild()) show('report')
  }
  // Views can also be changed from inside a screen (for example "Open the library").
  $effect(() => {
    if (BUILDER_VIEWS.includes(session.view)) lastBuilderView = session.view
  })
</script>

<svelte:window onhashchange={() => { const v = fromHash(); if (v) show(v) }} />

<div class="shell">
  <header class="top">
    <div class="identity">
      <Mark size={30} />
      <span class="wordmark">Skjald</span>
    </div>
    <nav class="nav" aria-label="Main">
      {#each nav as item (item.label)}
        <button type="button" class:active={item.active} aria-current={item.active ? 'page' : undefined} onclick={() => show(item.id)}>{item.label}</button>
      {/each}
    </nav>
    <div class="who">
      <label for="role">Viewing as</label>
      <select id="role" class="input" value={session.role} onchange={(e) => setRole(e.currentTarget.value)}>
        {#each Object.entries(USERS) as [key, u] (key)}<option value={key}>{u.name}, {u.role.toLowerCase()}</option>{/each}
      </select>
    </div>
  </header>

  {#if !session.introClosed}
    <div class="intro" role="note">
      <p><strong>A prototype of Skjald's report builder, with fictional data.</strong> Switch “Viewing as” to see each role's screens: technicians get Reports, the Library and Check a report; Templates is only for report designers and administrators. Nothing is saved.</p>
      <button type="button" class="btn quiet" onclick={() => (session.introClosed = true)}>Got it</button>
    </div>
  {/if}

  <p class="notice" role="status" aria-live="polite">
    {#if session.notice}<span>{session.notice}</span><button type="button" class="btn quiet" onclick={() => (session.notice = '')}>Dismiss</button>{/if}
  </p>

  <main>
    {#if BUILDER_VIEWS.includes(session.view) && canBuild()}<BuilderView onselect={show} />
    {:else if session.view === 'library'}<LibraryView />
    {:else if session.view === 'check'}<CheckView />
    {:else}<ReportView />{/if}
  </main>

  <footer class="foot">Phase 0 prototype of Skjald. Fictional sample data; nothing leaves this page.</footer>
</div>

<style>
  .shell { max-width: 1560px; margin: 0 auto; display: grid; gap: 12px;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 14px 28px; }
  .top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 20px;
    padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
  .identity { display: flex; align-items: center; gap: 10px; }
  .wordmark { font-family: var(--font-display); font-size: 22px; line-height: 1; }
  .nav { display: flex; flex-wrap: wrap; gap: 2px; }
  .nav button { min-height: 36px; padding: 0 14px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); font-weight: 600; font-size: 13.5px; cursor: pointer; }
  .nav button:hover { color: var(--text); background: var(--surface-subtle); }
  .nav button.active { color: var(--text); background: var(--surface-subtle); box-shadow: inset 0 -2px 0 var(--text); }
  .who { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-muted); }
  .who .input { width: auto; min-height: 34px; font-size: 13px; }
  .intro { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; padding: 10px 14px;
    border-radius: var(--radius-md); background: var(--info-bg); color: var(--info-text); font-size: 13px; }
  .intro p { margin: 0; max-width: 100ch; }
  .intro .btn { color: var(--info-text); }
  .notice { margin: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 13px; }
  .notice span { padding: 8px 12px; border-radius: var(--radius-md); background: var(--info-bg); color: var(--info-text); }
  main { min-width: 0; }
  .foot { font-size: 12px; color: var(--text-muted); text-align: center; }
  @media (max-width: 860px) {
    .top { display: grid; grid-template-columns: minmax(0, 1fr); }
    .nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .who { justify-content: space-between; }
    .who .input { flex: 1; min-width: 0; }
  }
</style>
