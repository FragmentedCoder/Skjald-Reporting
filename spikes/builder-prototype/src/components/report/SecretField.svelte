<script>
  // A secret in the technician's form: hidden until revealed with an MFA code, then shown for 30 seconds.
  // Every reveal is logged. The PDF shows only part of it (see maskSecret).
  import {onDestroy} from 'svelte'
  import {maskSecret} from '../../lib/pages.js'
  import {log} from '../../lib/state.svelte.js'

  let {question, value, onchange} = $props()
  const id = $derived(`ans-${question.key}`)

  let asking = $state(false)
  let code = $state('')
  let codeError = $state('')
  let left = $state(0)
  let timer = null

  function startReveal() {
    asking = true
    code = ''
    codeError = ''
  }
  function confirm() {
    if (!/^\d{6}$/.test(code.trim())) {
      codeError = 'Enter the 6-digit code from your authenticator app.'
      return
    }
    asking = false
    left = 30
    log(`Revealed “${question.label}”`)
    clearInterval(timer)
    timer = setInterval(() => {
      left -= 1
      if (left <= 0) clearInterval(timer)
    }, 1000)
  }
  function hide() {
    left = 0
    clearInterval(timer)
  }
  onDestroy(() => clearInterval(timer))
</script>

<div class="secret">
  <div class="line">
    <input {id} class="input mono" type={left > 0 ? 'text' : 'password'} autocomplete="off" spellcheck="false" value={value ?? ''}
      aria-describedby="{id}-pdf" oninput={(e) => onchange(e.currentTarget.value)} />
    {#if left > 0}
      <button type="button" class="btn" onclick={hide}>Hide now</button>
    {:else}
      <button type="button" class="btn" onclick={startReveal} disabled={asking || !value}>Reveal</button>
    {/if}
  </div>
  {#if left > 0}<span class="note" role="status">Shown for {left} more second{left === 1 ? '' : 's'}. This reveal was logged.</span>{/if}
  {#if asking}
    <div class="mfa" role="group" aria-label="Confirm it's you">
      <label for="{id}-code">Code from your authenticator app</label>
      <div class="line">
        <input id="{id}-code" class="input mono" inputmode="numeric" maxlength="6" autocomplete="one-time-code" bind:value={code}
          onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), confirm())} />
        <button type="button" class="btn primary" onclick={confirm}>Confirm</button>
        <button type="button" class="btn quiet" onclick={() => (asking = false)}>Cancel</button>
      </div>
      {#if codeError}<span class="error" role="alert">{codeError}</span>{:else}<span class="hint">Prototype: any six digits work.</span>{/if}
    </div>
  {/if}
  <span class="pdf" id="{id}-pdf"><span class="tag">In the PDF</span><span class="mono">{maskSecret(value, question.secret) || '—'}</span></span>
</div>

<style>
  .secret { display: grid; gap: 6px; }
  .line { display: flex; gap: 6px; align-items: center; }
  .line .input { flex: 1; min-width: 0; }
  .mfa { display: grid; gap: 4px; padding: 10px 12px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .mfa label { font-size: 12.5px; font-weight: 600; }
  .mfa .input { max-width: 120px; letter-spacing: 0.2em; }
  .note, .hint { font-size: 12px; color: var(--text-muted); }
  .error { font-size: 12px; color: var(--critical-text); }
  .pdf { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12.5px; }
  .tag { font-size: 11px; font-weight: 600; color: var(--text-muted); }
</style>
