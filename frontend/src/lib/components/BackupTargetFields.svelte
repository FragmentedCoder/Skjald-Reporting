<script lang="ts">
  // Where backups go, when and for how long: the admin panel's Backups page and the
  // setup wizard. Secrets are typed here and sent once; the server never sends them back.
  import { hourLabel, KINDS, type BackupTarget } from "#lib/backups.js";

  let {
    target = $bindable(),
    smbPassword = $bindable(),
    s3Secret = $bindable(),
    smbPasswordSet = false,
    s3SecretSet = false,
  }: {
    target: BackupTarget;
    smbPassword: string;
    s3Secret: string;
    smbPasswordSet?: boolean;
    s3SecretSet?: boolean;
  } = $props();

  const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
</script>

<fieldset class="checks kinds">
  <legend class="visually-hidden">Backup target</legend>
  {#each KINDS as option (option.kind)}
    <label class="check">
      <input type="radio" name="kind" value={option.kind} bind:group={target.kind} />
      <span>
        <span class="check-title">{option.name}</span>
        <span class="small muted">{option.about}</span>
      </span>
    </label>
  {/each}
</fieldset>

{#if target.kind === "smb"}
  <div class="grid">
    <div class="field">
      <label for="smb-host">Server</label>
      <input id="smb-host" class="input" required bind:value={target.smb_host} />
      <span class="hint">Its name or address, such as “nas.example.internal”.</span>
    </div>
    <div class="field">
      <label for="smb-share">Share</label>
      <input id="smb-share" class="input" required bind:value={target.smb_share} />
    </div>
    <div class="field">
      <label for="smb-path">Folder in the share</label>
      <input id="smb-path" class="input" bind:value={target.smb_path} />
    </div>
    <div class="field">
      <label for="smb-domain">Domain (optional)</label>
      <input id="smb-domain" class="input" bind:value={target.smb_domain} />
    </div>
    <div class="field">
      <label for="smb-user">User name</label>
      <input id="smb-user" class="input" required autocomplete="off" bind:value={target.smb_username} />
    </div>
    <div class="field">
      <label for="smb-password">Password</label>
      <input id="smb-password" class="input" type="password" autocomplete="new-password"
        placeholder={smbPasswordSet ? "Saved; type to replace it" : ""} bind:value={smbPassword} />
    </div>
  </div>
{:else if target.kind === "s3"}
  <div class="grid">
    <div class="field wide">
      <label for="s3-endpoint">Address</label>
      <input id="s3-endpoint" class="input" required placeholder="https://s3.eu-north-1.amazonaws.com"
        bind:value={target.s3_endpoint} />
    </div>
    <div class="field">
      <label for="s3-bucket">Bucket</label>
      <input id="s3-bucket" class="input" required bind:value={target.s3_bucket} />
    </div>
    <div class="field">
      <label for="s3-path">Folder in the bucket</label>
      <input id="s3-path" class="input" bind:value={target.s3_path} />
    </div>
    <div class="field">
      <label for="s3-region">Region (optional)</label>
      <input id="s3-region" class="input" bind:value={target.s3_region} />
    </div>
    <div class="field">
      <label for="s3-key">Access key</label>
      <input id="s3-key" class="input" required autocomplete="off" bind:value={target.s3_access_key_id} />
    </div>
    <div class="field">
      <label for="s3-secret">Secret key</label>
      <input id="s3-secret" class="input" type="password" autocomplete="new-password"
        placeholder={s3SecretSet ? "Saved; type to replace it" : ""} bind:value={s3Secret} />
    </div>
  </div>
{:else if target.kind === "local"}
  <p class="alert alert-warning">
    Backups kept on this server don't survive losing it. Use them alongside an SMB share or
    S3-compatible storage, or point SKJALD_BACKUP_DIR at a separate disk.
  </p>
{/if}

{#if target.kind !== "off"}
  <h3 class="subtitle">When and for how long</h3>
  <div class="grid">
    <div class="field">
      <label for="hour">Every night at</label>
      <select id="hour" class="input" bind:value={target.hour}>
        {#each HOURS as hour (hour)}
          <option value={hour}>{hourLabel(hour)}</option>
        {/each}
      </select>
    </div>
    <div class="field">
      <label for="keep">Keep for (days)</label>
      <input id="keep" class="input" type="number" min="7" max="3650" required bind:value={target.keep_days} />
    </div>
  </div>
  <p class="small muted">
    Older snapshots are deleted. A customer deleted in Skjald stays in older snapshots until
    they age out: after {target.keep_days} days, no backup holds anything of them.
  </p>
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
</style>
