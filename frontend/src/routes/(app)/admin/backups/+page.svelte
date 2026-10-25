<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import {
    RUN_NAMES,
    runSummary,
    type BackupRun,
    type BackupStatus,
    type BackupTarget,
    type RunKind,
  } from "#lib/backups.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import BackupTargetFields from "#lib/components/BackupTargetFields.svelte";
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
    <BackupTargetFields bind:target={form} bind:smbPassword bind:s3Secret
      smbPasswordSet={status.smb_password_set} s3SecretSet={status.s3_secret_set} />

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
      Restoring replaces Skjald's data with a backup, so it's done on the server with the
      recovery kit at hand. Skjald stops while it runs, and the data that was there is kept
      beside it.
    </p>
    <Command command="sudo skjald restore" />
    <p class="small muted">
      The newest backup unless you add --snapshot and its ID. A backup made before the master
      key was rotated asks for the master key it was made under. On a new server, put the
      kit's master key in place first: run the installer with --restore-master-key.
    </p>
  </section>
{/if}

<style>
  .nowrap {
    white-space: nowrap;
  }
</style>
