<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
  import { onMount } from "svelte";
  import { pageTitle } from "#lib/branding.svelte.js";
  import { api, ApiError } from "#lib/api.js";
  import {
    ACTION_GROUPS,
    describe,
    filterParams,
    type AuditEntry,
    type AuditFilters,
  } from "#lib/audit.js";
  import Pill from "#lib/components/Pill.svelte";
  import { isoTime, time } from "#lib/format.js";
  import { can, session } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  interface ChainStatus {
    ok: boolean;
    entries_checked: number;
    first_bad_seq: number | null;
    problem: string | null;
    stamps: number;
    stamps_ok: boolean;
    stamp_problem: string | null;
    last_stamped_seq: number | null;
    last_stamped_at: string | null;
    tsa_url: string;
  }

  interface StampRun {
    id: number;
    state: "queued" | "running" | "done" | "failed";
    result: { seq?: number } | null;
    error: string | null;
  }

  let filters = $state<AuditFilters>({ action: "", actor: "", since: "", until: "" });
  let applied = $state<AuditFilters>({ action: "", actor: "", since: "", until: "" });
  let entries = $state<AuditEntry[]>([]);
  let nextBefore = $state<number | null>(null);
  let actions = $state<string[]>([]);
  let chain = $state<ChainStatus | null>(null);
  let checking = $state(false);
  let checkedAt = $state<string | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let tsaUrl = $state("");
  let stamping = $state(false);
  const mayAdminister = $derived(can(session.current, "administer"));
  const tsaHost = $derived(chain ? hostOf(chain.tsa_url) : "");

  function hostOf(url: string): string {
    try {
      return new URL(url).host;
    } catch {
      return url;
    }
  }

  async function load(more = false) {
    busy = true;
    error = null;
    try {
      const extra: Record<string, string> = more && nextBefore ? { before: String(nextBefore) } : {};
      const page = await api<{ entries: AuditEntry[]; next_before: number | null }>(
        "GET",
        `/audit${filterParams(applied, extra)}`,
      );
      entries = more ? [...entries, ...page.entries] : page.entries;
      nextBefore = page.next_before;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The audit log could not be loaded.";
    } finally {
      busy = false;
    }
  }

  // The last result stays on screen while checking again, so nothing jumps.
  async function checkChain() {
    checking = true;
    try {
      chain = await api<ChainStatus>("GET", "/audit/verify");
      tsaUrl = chain.tsa_url;
      checkedAt = new Date().toISOString();
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The chain could not be checked.";
    } finally {
      checking = false;
    }
  }

  onMount(async () => {
    await load();
    actions = await api<string[]>("GET", "/audit/actions").catch(() => []);
    await checkChain();
  });

  // Ask the worker for a timestamp now, and follow it until it's done.
  async function stampNow() {
    stamping = true;
    try {
      let run = await api<StampRun>("POST", "/audit/stamps/run");
      while ((run.state === "queued" && !run.error) || run.state === "running") {
        await new Promise((done) => setTimeout(done, 2000));
        run = await api<StampRun>("GET", `/audit/stamps/runs/${run.id}`);
      }
      if (run.state === "done") toast(`Timestamped entry ${run.result?.seq}.`, "ok");
      else toast(run.error ?? "The timestamp couldn't be had.", "critical");
      await checkChain();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    } finally {
      stamping = false;
    }
  }

  async function saveAuthority(event: SubmitEvent) {
    event.preventDefault();
    try {
      chain = await api<ChainStatus>("PUT", "/audit/stamps/authority", { tsa_url: tsaUrl });
      toast("Timestamp authority saved.", "ok", { key: "saved" });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    }
  }

  function apply(event: SubmitEvent) {
    event.preventDefault();
    applied = { ...filters };
    load();
  }

  function clear() {
    filters = { action: "", actor: "", since: "", until: "" };
    applied = { ...filters };
    load();
  }
</script>

<svelte:head><title>{pageTitle("Audit log · Admin")}</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Audit log</h1>
    <p class="small muted">
      Every sign-in, change and export, in a hash chain that shows any edit or removal.
    </p>
  </div>
  <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- an API download, not a page -->
  <a class="button button-secondary" href="/api/audit/export{filterParams(applied)}" download>
    <Download size={18} aria-hidden="true" />
    Export CSV
  </a>
</div>

<div class="chain" aria-live="polite">
  {#if chain === null}
    <span class="small muted">Checking the chain…</span>
  {:else if chain.ok}
    <Pill tone="ok" text="Chain intact" />
    <span class="small muted">
      All {chain.entries_checked.toLocaleString("en-GB")} entries check out{checkedAt
        ? ` (checked ${time(checkedAt)})`
        : ""}.
    </span>
  {:else}
    <Pill tone="critical" text="Chain broken" />
    <span class="small">Entry {chain.first_bad_seq}: {chain.problem}.</span>
  {/if}
  <button class="link-button" type="button" disabled={checking} onclick={checkChain}>
    {checking ? "Checking…" : "Check again"}
  </button>
</div>

{#if chain}
  <div class="chain">
    {#if !chain.stamps_ok}
      <Pill tone="critical" text="Timestamps don't match" />
      <span class="small">{chain.stamp_problem}</span>
    {:else if chain.stamps === 0 || !chain.last_stamped_at}
      <Pill tone="neutral" text="Not timestamped yet" />
      <span class="small muted">The worker asks {tsaHost} to timestamp the newest entry once a day.</span>
    {:else}
      <Pill tone="ok" text="Timestamped" />
      <span class="small muted">
        Entry {chain.last_stamped_seq} timestamped {isoTime(chain.last_stamped_at)} by {tsaHost}; all
        {chain.stamps.toLocaleString("en-GB")} timestamps still match the log.
      </span>
    {/if}
    {#if mayAdminister}
      <button class="link-button" type="button" disabled={stamping} onclick={stampNow}>
        {stamping ? "Timestamping…" : "Timestamp now"}
      </button>
    {/if}
  </div>
  {#if mayAdminister}
    <details class="authority">
      <summary class="small">Timestamp authority</summary>
      <form class="authority-form" onsubmit={saveAuthority}>
        <div class="field">
          <label for="tsa">Address of an RFC 3161 timestamp authority</label>
          <input id="tsa" class="input" type="url" required maxlength="300" bind:value={tsaUrl} />
          <span class="hint">
            Only a fingerprint of the newest entry is sent. Free ones include DigiCert's
            (http://timestamp.digicert.com) and FreeTSA (https://freetsa.org/tsr).
          </span>
        </div>
        <div><button class="button button-secondary" type="submit">Save</button></div>
      </form>
    </details>
  {/if}
{/if}

<form class="section filters" onsubmit={apply}>
  <div class="field">
    <label for="action">What</label>
    <select id="action" class="input" bind:value={filters.action}>
      <option value="">Everything</option>
      <optgroup label="Groups">
        {#each ACTION_GROUPS as group (group.value)}
          <option value={group.value}>{group.label}</option>
        {/each}
      </optgroup>
      <optgroup label="Single actions">
        {#each actions as action (action)}<option value={action}>{action}</option>{/each}
      </optgroup>
    </select>
  </div>
  <div class="field">
    <label for="actor">Who</label>
    <input id="actor" class="input" placeholder="Username" autocapitalize="none"
      bind:value={filters.actor} />
  </div>
  <div class="field">
    <label for="since">From</label>
    <input id="since" class="input" type="date" bind:value={filters.since} />
  </div>
  <div class="field">
    <label for="until">To</label>
    <input id="until" class="input" type="date" bind:value={filters.until} />
  </div>
  <div class="button-row filter-buttons">
    <button class="button button-primary" type="submit" disabled={busy}>Show</button>
    <button class="button button-secondary" type="button" onclick={clear}>Clear</button>
  </div>
</form>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

<div class="section table-wrap">
  <table class="table">
    <thead>
      <tr><th>#</th><th>When (UTC)</th><th>Who</th><th>What</th><th>Details</th><th>Address</th></tr>
    </thead>
    <tbody>
      {#each entries as entry (entry.seq)}
        <tr>
          <td class="mono muted">{entry.seq}</td>
          <td class="nowrap mono" title={entry.occurred_at}>{isoTime(entry.occurred_at)}</td>
          <td>{entry.actor_name ?? "—"}</td>
          <td class="mono">{entry.action}</td>
          <td class="details">{describe(entry.details)}</td>
          <td class="mono">{entry.ip ?? "—"}</td>
        </tr>
      {:else}
        <tr><td colspan="6" class="muted">Nothing matches these filters.</td></tr>
      {/each}
    </tbody>
  </table>
</div>

{#if nextBefore}
  <div>
    <button class="button button-secondary" type="button" disabled={busy} onclick={() => load(true)}>
      Load more
    </button>
  </div>
{/if}

<style>
  .authority {
    margin-top: calc(-1 * var(--space-2));
  }
  .authority summary {
    cursor: pointer;
  }
  .authority-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 560px;
    margin-top: var(--space-3);
  }
  .chain {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }
  .filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    align-items: end;
    gap: var(--space-4);
  }
  .filter-buttons {
    align-self: end;
  }
  .nowrap {
    white-space: nowrap;
  }
  .details {
    max-width: 360px;
    overflow-wrap: anywhere;
  }
</style>
