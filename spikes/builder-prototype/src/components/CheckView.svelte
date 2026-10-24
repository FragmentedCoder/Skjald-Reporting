<script>
  // "Check a signed report": the results shown for the samples come from spikes/pdf-signing/check_report.py,
  // run on the spike's signed report and on a copy with one byte changed.
  import samples from '../lib/check-samples.json'
  import {log} from '../lib/state.svelte.js'

  const VERDICTS = {
    valid: {pill: 'ok', label: 'Valid', title: 'Signed and unchanged', text: 'Every signature is intact and trusted, and nothing but later signatures and validation data was added after signing.'},
    changed: {pill: 'critical', label: 'Changed', title: 'Changed after it was signed', text: 'The file no longer matches what was signed. Don’t rely on its content; ask for the original, or compare it with the archived copy.'},
    untrusted: {pill: 'warning', label: 'Check the signer', title: 'Signed, but the signer is not trusted', text: 'The signatures are intact, but the certificate behind one of them does not lead to a trusted root.'},
    invalid: {pill: 'critical', label: 'Not valid', title: 'A signature is not valid', text: 'At least one signature failed its checks.'},
    unsigned: {pill: 'plain', label: 'Not signed', title: 'This PDF has no signatures', text: 'Nothing in it proves who made it or that it is unchanged.'},
    unreadable: {pill: 'critical', label: 'Not readable', title: 'This is not a readable PDF', text: 'The file is damaged or not a PDF.'},
    browser: {pill: 'plain', label: 'Not checked', title: 'Not checked in the prototype', text: 'The prototype can’t verify signatures in your browser. In Skjald the file goes to the signer service, and you get the full result, like the two samples show.'},
  }

  let result = $state(null)
  let dragging = $state(false)
  let error = $state('')

  const fmt = (iso) => new Date(iso).toLocaleString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'})
  const issuedHashes = Object.fromEntries(samples.samples.filter((s) => s.issued_as).map((s) => [s.sha256, s.issued_as]))

  function showSample(i) {
    error = ''
    result = samples.samples[i]
    log(`Checked ${result.file}: ${VERDICTS[result.verdict].label.toLowerCase()}`)
  }

  async function checkFile(file) {
    error = ''
    if (!file) return
    if (file.size > 50 * 1024 * 1024) return (error = 'Files can be up to 50 MB.')
    const bytes = new Uint8Array(await file.arrayBuffer())
    const head = new TextDecoder('latin1').decode(bytes.slice(0, 5))
    const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((b) => b.toString(16).padStart(2, '0')).join('')
    const text = new TextDecoder('latin1').decode(bytes)
    const signatures = (text.match(/\/ByteRange\s*\[/g) ?? []).length
    result = {
      file: file.name, sha256, size_kb: Math.max(1, Math.round(file.size / 1024)), issued_as: issuedHashes[sha256] ?? null,
      verdict: head === '%PDF-' ? 'browser' : 'unreadable', found: signatures, signatures: [], browser: true,
    }
    log(`Checked ${file.name} in the prototype (not verified)`)
  }
  function drop(e) {
    e.preventDefault()
    dragging = false
    checkFile(e.dataTransfer?.files?.[0])
  }
  const v = $derived(result ? VERDICTS[result.verdict] : null)
</script>

<div class="check">
  <header class="head">
    <h1>Check a signed report</h1>
    <p>Got a report back from a customer, or found one in a mailbox? Check whether it’s genuine. Skjald checks every signature and its timestamp, whether anything changed after signing, whether it is still PDF/A, and whether this exact file is one Skjald issued.</p>
  </header>

  <div class="panel drop" class:dragging role="region" aria-label="Choose a PDF"
    ondragover={(e) => { e.preventDefault(); dragging = true }} ondragleave={() => (dragging = false)} ondrop={drop}>
    <div class="drop-inner">
      <span class="big" aria-hidden="true">▤</span>
      <span class="drop-label">Drop a PDF here</span>
      <input id="check-file" class="file-input" type="file" accept="application/pdf,.pdf" onchange={(e) => checkFile(e.currentTarget.files?.[0])} />
      <label for="check-file" class="btn primary">Choose a PDF</label>
      <span class="hint">The file is checked and then discarded; it is not stored. Each check is logged.</span>
    </div>
    <div class="samples">
      <span class="overline">Or try a sample</span>
      <button type="button" class="btn" onclick={() => showSample(0)}>The signed sample report</button>
      <button type="button" class="btn" onclick={() => showSample(1)}>A copy with one byte changed</button>
    </div>
    {#if error}<span class="error" role="alert">{error}</span>{/if}
  </div>

  {#if result && v}
    <section class="panel result" aria-live="polite" aria-label="Result">
      <div class="verdict {v.pill}">
        <span class="pill {v.pill}">{v.label}</span>
        <div><h2>{v.title}</h2><p>{v.text}</p></div>
      </div>

      <dl class="facts">
        <div><dt>File</dt><dd>{result.file}</dd></div>
        <div><dt>Issued by Skjald</dt><dd>{#if result.issued_as}Yes: this exact file is report <span class="mono">{result.issued_as}</span>{:else}No report in Skjald has this exact file{/if}</dd></div>
        {#if !result.browser}
          <div><dt>Pages</dt><dd>{result.pages}</dd></div>
          <div><dt>PDF/A</dt><dd>{result.pdfa ? 'Yes, PDF/A-3' : 'No'}</dd></div>
        {:else}
          <div><dt>Signatures found</dt><dd>{result.found} (not verified)</dd></div>
        {/if}
        <div><dt>Size</dt><dd>{result.size_kb} KB</dd></div>
        <div class="hash"><dt>SHA-256</dt><dd class="mono">{result.sha256}</dd></div>
      </dl>

      {#if result.signatures.length}
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">Signed by</th><th scope="col">When</th><th scope="col">Signature</th><th scope="col">Signer</th><th scope="col">After signing</th></tr></thead>
            <tbody>
              {#each result.signatures as s (s.field)}
                <tr>
                  <td><strong>{s.role}</strong><span class="sub">{s.name}{s.organisation && !s.name.includes(s.organisation) ? `, ${s.organisation}` : ''}</span></td>
                  <td>{s.signed_at ? fmt(s.signed_at) : '—'}<span class="sub">{s.timestamp_trusted ? `Timestamp by ${s.timestamp_by}` : 'No trusted timestamp'}</span></td>
                  <td>{#if s.intact}<span class="pill ok">Intact</span>{:else}<span class="pill critical">Broken</span>{/if}</td>
                  <td>{#if s.trusted}<span class="pill ok">Trusted</span>{:else}<span class="pill warning">Not trusted</span>{/if}</td>
                  <td>{s.intact ? s.changes_after : 'The signed content was changed'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
      <p class="note">The samples were checked with the spike's test certificate authority. In Skjald, signatures from your own signing CA and from certificates you buy are trusted.</p>
    </section>
  {/if}
</div>

<style>
  .check { display: grid; gap: 14px; max-width: 980px; }
  .head { display: grid; gap: 4px; }
  h1 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 26px; }
  .head p { margin: 0; color: var(--text-muted); max-width: 78ch; }
  .drop { display: grid; gap: 14px; padding: 18px; border-style: dashed; border-width: 2px; }
  .drop.dragging { border-color: var(--link); background: var(--info-bg); }
  .drop-inner { display: grid; justify-items: center; gap: 6px; text-align: center; }
  .big { font-size: 30px; color: var(--text-muted); }
  .drop-label { font-weight: 600; }
  /* The native file input is hidden but stays focusable; its label is the visible button. */
  .file-input { position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; }
  .file-input:focus-visible + .btn { outline: 2px solid var(--link); outline-offset: 2px; }
  .samples { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px; }
  .hint { font-size: 12px; color: var(--text-muted); }
  .error { font-size: 12.5px; color: var(--critical-text); text-align: center; }
  .result { display: grid; gap: 14px; padding: 16px; }
  .verdict { display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .verdict.ok { background: var(--ok-bg); }
  .verdict.critical { background: var(--critical-bg); }
  .verdict.warning { background: var(--warning-bg); }
  .verdict h2 { margin: 0; font-size: 19px; }
  .verdict p { margin: 2px 0 0; font-size: 13.5px; max-width: 72ch; }
  .verdict .pill { margin-top: 3px; }
  .facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 20px; margin: 0; font-size: 13px; }
  .facts div { display: grid; gap: 1px; min-width: 0; }
  .facts .hash { grid-column: 1 / -1; }
  .facts dt { font-size: 12px; font-weight: 600; color: var(--text-muted); }
  .facts dd { margin: 0; overflow-wrap: anywhere; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 12px; font-weight: 600; color: var(--text-muted); padding: 6px 10px; border-bottom: 1px solid var(--border-strong); }
  td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  .sub { display: block; font-size: 12px; color: var(--text-muted); }
  .note { margin: 0; font-size: 12.5px; color: var(--text-muted); }
  @media (max-width: 600px) { .facts { grid-template-columns: minmax(0, 1fr); } }
</style>
