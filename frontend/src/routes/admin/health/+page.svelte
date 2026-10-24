<script lang="ts">
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import { pageTitle } from "$lib/branding.svelte";
  import Pill from "$lib/components/Pill.svelte";
  import { bytes, dateTime, since } from "$lib/format";

  type Status = "ok" | "warning" | "problem" | "off";

  interface Check {
    key: string;
    label: string;
    status: Status;
    detail: string;
  }

  interface Health {
    checked_at: string;
    started_at: string;
    address: string;
    setup_completed_at: string | null;
    checks: Check[];
    usage: {
      disk_total_bytes: number;
      disk_free_bytes: number;
      database_bytes: number;
      images_bytes: number;
      audit_entries: number;
      users: number;
      active_users: number;
      sessions: number;
    };
    versions: {
      skjald: string;
      python: string;
      sqlite: string;
      sqlcipher: string;
      schema_version: string | null;
      operating_system: string;
      kernel: string;
    };
    packages: { name: string; version: string }[];
  }

  const PILLS: Record<Status, { tone: "ok" | "warning" | "critical" | "neutral"; text: string }> = {
    ok: { tone: "ok", text: "OK" },
    warning: { tone: "warning", text: "Warning" },
    problem: { tone: "critical", text: "Problem" },
    off: { tone: "neutral", text: "Off" },
  };
  // Authenticator codes change every 30 seconds; a server clock this far off breaks them.
  const CLOCK_TOLERANCE_S = 30;

  let health = $state<Health | null>(null);
  let skewSeconds = $state(0);
  let error = $state<string | null>(null);
  let checking = $state(false);

  // The server's checks, plus one only the browser can do: compare the clocks.
  const checks = $derived.by((): Check[] => {
    if (!health) return [];
    const off = Math.abs(skewSeconds);
    const clock: Check =
      off > CLOCK_TOLERANCE_S
        ? {
            key: "clock",
            label: "Clock",
            status: "warning",
            detail: `The server's clock and this computer's differ by ${off} seconds. Authenticator codes need the server's clock to be right.`,
          }
        : {
            key: "clock",
            label: "Clock",
            status: "ok",
            detail: "The server's clock matches this computer's.",
          };
    return [...health.checks, clock];
  });
  const worst = $derived(
    checks.some((c) => c.status === "problem")
      ? "problem"
      : checks.some((c) => c.status === "warning")
        ? "warning"
        : "ok",
  );

  async function check() {
    checking = true;
    error = null;
    try {
      const asked = Date.now();
      const found = await api<Health>("GET", "/admin/health");
      const answered = Date.now();
      skewSeconds = Math.round((Date.parse(found.checked_at) - (asked + answered) / 2) / 1000);
      health = found;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The server could not be checked.";
    } finally {
      checking = false;
    }
  }

  onMount(check);
</script>

<svelte:head><title>{pageTitle("Server health · Admin")}</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Server health</h1>
    <p class="small muted">
      {#if health}Checked {dateTime(health.checked_at)}.{:else}Checking the server…{/if}
    </p>
  </div>
  <button class="button button-secondary" type="button" disabled={checking} onclick={check}>
    <RefreshCw size={16} aria-hidden="true" />
    {checking ? "Checking…" : "Check again"}
  </button>
</div>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

{#if health}
  <section class="section" aria-labelledby="checks-title">
    <div class="heading-row">
      <h2 class="section-title" id="checks-title">Checks</h2>
      <Pill tone={PILLS[worst].tone}
        text={worst === "ok" ? "All OK" : worst === "warning" ? "Needs a look" : "Needs action"} />
    </div>
    <ul class="checks-list">
      {#each checks as item (item.key)}
        <li>
          <Pill tone={PILLS[item.status].tone} text={PILLS[item.status].text} />
          <div>
            <p class="check-label">{item.label}</p>
            <p class="small muted">{item.detail}</p>
          </div>
        </li>
      {/each}
    </ul>
  </section>

  <section class="section" aria-labelledby="space-title">
    <h2 class="section-title" id="space-title">Space</h2>
    <div class="disk">
      <label for="disk-meter" class="check-label">Disk</label>
      <meter id="disk-meter" min="0" max={health.usage.disk_total_bytes}
        value={health.usage.disk_total_bytes - health.usage.disk_free_bytes}
        high={health.usage.disk_total_bytes * 0.85} optimum="0"></meter>
      <p class="small muted">
        {bytes(health.usage.disk_free_bytes)} free of {bytes(health.usage.disk_total_bytes)}
      </p>
    </div>
    <dl class="facts">
      <dt>Database</dt>
      <dd>{bytes(health.usage.database_bytes)}</dd>
      <dt>Pictures and logo</dt>
      <dd>{bytes(health.usage.images_bytes)}</dd>
      <dt>Audit log</dt>
      <dd>{health.usage.audit_entries.toLocaleString("en-GB")} entries</dd>
      <dt>Users</dt>
      <dd>{health.usage.active_users} active of {health.usage.users}</dd>
      <dt>Signed-in sessions</dt>
      <dd>{health.usage.sessions}</dd>
    </dl>
  </section>

  <section class="section" aria-labelledby="server-title">
    <h2 class="section-title" id="server-title">Server</h2>
    <dl class="facts">
      <dt>Address</dt>
      <dd class="mono">{health.address}</dd>
      <dt>Running for</dt>
      <dd>{since(health.started_at)} (since {dateTime(health.started_at)})</dd>
      <dt>Set up</dt>
      <dd>{dateTime(health.setup_completed_at, "Not finished")}</dd>
    </dl>
  </section>

  <section class="section" aria-labelledby="versions-title">
    <h2 class="section-title" id="versions-title">Software</h2>
    <dl class="facts">
      <dt>Skjald</dt>
      <dd class="mono">{health.versions.skjald}</dd>
      <dt>Database schema</dt>
      <dd class="mono">{health.versions.schema_version ?? "—"}</dd>
      <dt>Python</dt>
      <dd class="mono">{health.versions.python}</dd>
      <dt>SQLite</dt>
      <dd class="mono">{health.versions.sqlite}</dd>
      <dt>SQLCipher</dt>
      <dd class="mono">{health.versions.sqlcipher}</dd>
      <dt>Operating system</dt>
      <dd>{health.versions.operating_system}</dd>
      <dt>Kernel</dt>
      <dd class="mono">{health.versions.kernel}</dd>
    </dl>
    <details>
      <summary>Python packages ({health.packages.length})</summary>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Package</th><th>Version</th></tr></thead>
          <tbody>
            {#each health.packages as item (item.name)}
              <tr><td class="mono">{item.name}</td><td class="mono">{item.version}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </details>
  </section>
{/if}

<style>
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }
  .checks-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .checks-list li {
    display: grid;
    grid-template-columns: 6.5rem minmax(0, 1fr);
    align-items: start;
    justify-items: start;
    gap: var(--space-3);
  }
  .check-label {
    font: var(--type-label);
  }
  .disk {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    max-width: 520px;
  }
  meter {
    width: 100%;
    height: 12px;
  }
  details {
    margin-top: var(--space-2);
  }
  summary {
    font: var(--type-label);
    cursor: pointer;
  }
</style>
