<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import {
    hourLabel,
    KINDS,
    RUN_NAMES,
    runSummary,
    type BackupRun,
    type BackupStatus,
    type BackupTarget,
    type RunKind,
  } from "#lib/backups.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Command from "#lib/components/Command.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import { dateTime } from "#lib/format.js";
  import { withStepUp } from "#lib/stepUp.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  // Backups: where they go, when, for how long, and how they fare. The worker does
  // the work; this page queues it and follows it.
  let status = $state<BackupStatus | null>(null);
  let form = $state<BackupTarget | null>(null);
  let smbPassword = $state("");
  let s3Secret = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);
  let following = $state<BackupRun | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
  const TONES = { done: "ok", failed: "critical", running: "info", queued: "neutral" } as const;
  const STATES = { done: "OK", failed: "Failed", running: "Running", queued: "Waiting" } as const;

  function use(found: BackupStatus) {
    status = found;
    form = { ...found.target };
    smbPassword = "";
    s3Secret = "";
  }

  async function load() {
    try {
      use(await api<BackupStatus>("GET", "/admin/backups"));
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not available.";
    }
  }

  onMount(load);
  onDestroy(() => clearTimeout(timer));

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!form) return;
    busy = true;
    try {
      use(await withStepUp(() => api<BackupStatus>("PUT", "/admin/backups", {
        ...form,
        smb_password: smbPassword === "" ? null : smbPassword,
        s3_secret_access_key: s3Secret === "" ? null : s3Secret,
      })));
      toast("Backup settings saved.", "ok", { key: "saved" });
    } catch (e) {
      if (e instanceof ApiError && e.reason === "step_up_cancelled") return;
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    } finally {
      busy = false;
    }
  }

  // Queue the work, then ask how it's going every two seconds until it's done.
  async function runNow(kind: RunKind) {
    try {
      following = await api<BackupRun>("POST", `/admin/backups/run/${kind}`);
      void follow();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    }
  }

  async function follow() {
    if (!following) return;
    const run = await api<BackupRun>("GET", `/admin/backups/runs/${following.id}`).catch(() => null);
    if (run) following = run;
    if (run && (run.state === "done" || run.state === "failed" || (run.state === "queued" && run.error))) {
      toast(`${RUN_NAMES[run.kind]}: ${runSummary(run)}`, run.state === "done" ? "ok" : "critical");
      following = null;
      await load();
      return;
    }
    timer = setTimeout(follow, 2000);
  }
</script>

<svelte:head><title>{pageTitle("Backups · Admin")}</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Backups</h1>
    <p class="small muted">
      Encrypted with the backup key from the recovery kit: without the kit, a backup can't be
      restored.
    </p>
  </div>
</div>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

{#if status && form}
  <section class="section" aria-labelledby="state-title">
    <h2 class="section-title" id="state-title">How it stands</h2>
    <dl class="facts">
      <dt>Last backup</dt>
      <dd>
        {#if status.last_backup}
          {dateTime(status.last_backup.finished_at)}: {runSummary(status.last_backup)}
        {:else}
          None yet
        {/if}
      </dd>
      <dt>Next backup</dt>
      <dd>
        {#if !status.next_backup_at}
          None: backups are off
        {:else if new Date(status.next_backup_at).getTime() <= Date.now() + 60_000}
          Due now: the worker starts it within a minute
        {:else}
          {dateTime(status.next_backup_at)}
        {/if}
      </dd>
      <dt>Last restore test</dt>
      <dd>
        {#if status.last_restore_test}
          {dateTime(status.last_restore_test.finished_at)}:
          {status.last_restore_test.state === "done" ? "" : "failed. "}{runSummary(status.last_restore_test)}
        {:else}
          None yet. The worker tests one a week, after a backup.
        {/if}
      </dd>
      {#if status.repository}
        <dt>Repository</dt>
        <dd class="mono">{status.repository}</dd>
      {/if}
    </dl>
    {#if following}
      <p class="small" role="status">{RUN_NAMES[following.kind]}: {runSummary(following)}…</p>
    {/if}
    <div class="button-row">
      <button class="button button-primary" type="button" disabled={!!following || status.target.kind === "off"}
        onclick={() => runNow("backup")}>Back up now</button>
      <button class="button button-secondary" type="button"
        disabled={!!following || !status.last_backup} onclick={() => runNow("restore_test")}>
        Test a restore now
      </button>
    </div>
  </section>

  <form class="section stack" onsubmit={save} aria-labelledby="target-title">
    <h2 class="section-title" id="target-title">Where backups go</h2>
    <fieldset class="checks kinds">
      <legend class="visually-hidden">Backup target</legend>
      {#each KINDS as option (option.kind)}
        <label class="check">
          <input type="radio" name="kind" value={option.kind} bind:group={form.kind} />
          <span>
            <span class="check-title">{option.name}</span>
            <span class="small muted">{option.about}</span>
          </span>
        </label>
      {/each}
    </fieldset>

    {#if form.kind === "smb"}
      <div class="grid">
        <div class="field">
          <label for="smb-host">Server</label>
          <input id="smb-host" class="input" required bind:value={form.smb_host} />
          <span class="hint">Its name or address, such as “nas.example.internal”.</span>
        </div>
        <div class="field">
          <label for="smb-share">Share</label>
          <input id="smb-share" class="input" required bind:value={form.smb_share} />
        </div>
        <div class="field">
          <label for="smb-path">Folder in the share</label>
          <input id="smb-path" class="input" bind:value={form.smb_path} />
        </div>
        <div class="field">
          <label for="smb-domain">Domain (optional)</label>
          <input id="smb-domain" class="input" bind:value={form.smb_domain} />
        </div>
        <div class="field">
          <label for="smb-user">User name</label>
          <input id="smb-user" class="input" required autocomplete="off" bind:value={form.smb_username} />
        </div>
        <div class="field">
          <label for="smb-password">Password</label>
          <input id="smb-password" class="input" type="password" autocomplete="new-password"
            placeholder={status.smb_password_set ? "Saved; type to replace it" : ""} bind:value={smbPassword} />
        </div>
      </div>
    {:else if form.kind === "s3"}
      <div class="grid">
        <div class="field wide">
          <label for="s3-endpoint">Address</label>
          <input id="s3-endpoint" class="input" required placeholder="https://s3.eu-north-1.amazonaws.com"
            bind:value={form.s3_endpoint} />
        </div>
        <div class="field">
          <label for="s3-bucket">Bucket</label>
          <input id="s3-bucket" class="input" required bind:value={form.s3_bucket} />
        </div>
        <div class="field">
          <label for="s3-path">Folder in the bucket</label>
          <input id="s3-path" class="input" bind:value={form.s3_path} />
        </div>
        <div class="field">
          <label for="s3-region">Region (optional)</label>
          <input id="s3-region" class="input" bind:value={form.s3_region} />
        </div>
        <div class="field">
          <label for="s3-key">Access key</label>
          <input id="s3-key" class="input" required autocomplete="off" bind:value={form.s3_access_key_id} />
        </div>
        <div class="field">
          <label for="s3-secret">Secret key</label>
          <input id="s3-secret" class="input" type="password" autocomplete="new-password"
            placeholder={status.s3_secret_set ? "Saved; type to replace it" : ""} bind:value={s3Secret} />
        </div>
      </div>
    {:else if form.kind === "local"}
      <p class="alert alert-warning">
        Backups kept on this server don't survive losing it. Use them alongside an SMB share or
        S3-compatible storage, or point SKJALD_BACKUP_DIR at a separate disk.
      </p>
    {/if}

    {#if form.kind !== "off"}
      <h3 class="subtitle">When and for how long</h3>
      <div class="grid">
        <div class="field">
          <label for="hour">Every night at</label>
          <select id="hour" class="input" bind:value={form.hour}>
            {#each HOURS as hour (hour)}
              <option value={hour}>{hourLabel(hour)}</option>
            {/each}
          </select>
        </div>
        <div class="field">
          <label for="keep">Keep for (days)</label>
          <input id="keep" class="input" type="number" min="7" max="3650" required bind:value={form.keep_days} />
        </div>
      </div>
      <p class="small muted">
        Older snapshots are deleted. A customer deleted in Skjald stays in older snapshots until
        they age out: after {form.keep_days} days, no backup holds anything of them.
      </p>
    {/if}

    <div class="button-row">
      <button class="button button-primary" type="submit" disabled={busy}>Save</button>
      <button class="button button-secondary" type="button"
        disabled={!!following || status.target.kind === "off"} onclick={() => runNow("backup_check")}>
        Check the connection
      </button>
    </div>
    <p class="small muted">Changing where backups go asks you to confirm it's you. The connection check uses what's saved.</p>
  </form>

  <section class="section" aria-labelledby="runs-title">
    <h2 class="section-title" id="runs-title">Recent runs</h2>
    {#if status.runs.length}
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>When</th><th>What</th><th>How it went</th><th>Asked for by</th></tr></thead>
          <tbody>
            {#each status.runs as run (run.id)}
              <tr>
                <td class="nowrap">{dateTime(run.finished_at ?? run.started_at ?? run.created_at)}</td>
                <td>{RUN_NAMES[run.kind]}</td>
                <td>
                  <Pill tone={TONES[run.state]} text={STATES[run.state]} />
                  <span class="small">{runSummary(run)}</span>
                </td>
                <td>{run.requested_by ?? "The schedule"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="muted">No runs yet.</p>
    {/if}
  </section>

  <section class="section" aria-labelledby="restore-title">
    <h2 class="section-title" id="restore-title">Restoring</h2>
    <p class="small">
      Restoring replaces Skjald's data with a backup, so it's done on the server, with Skjald
      stopped and the recovery kit at hand. The data that was there is kept beside it.
    </p>
    <Command command="docker compose stop app worker" />
    <Command command="docker compose run --rm worker python -m app.restore" />
    <Command command="docker compose up -d" />
    <p class="small muted">
      On a new server, put the kit's master key in place first: run the installer with
      --restore-master-key.
    </p>
  </section>
{/if}

<style>
  .kinds {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: var(--space-4);
    max-width: 760px;
  }
  .wide {
    grid-column: 1 / -1;
  }
  .subtitle {
    margin: var(--space-2) 0 0;
    font: var(--type-label);
  }
  .nowrap {
    white-space: nowrap;
  }
</style>
