<script lang="ts">
  // Which certificate Skjald serves: the admin panel's Certificate page and the setup
  // wizard. Files are read here and sent once; the key never comes back.
  import Command from "./Command.svelte";
  import { MODES, RESET_COMMAND, type Certificate, type TlsChoice } from "#lib/tls.js";

  let {
    choice = $bindable(),
    host,
    uploaded = null,
    resetHint = true,
  }: {
    choice: TlsChoice;
    host: string;
    uploaded?: Certificate | null;
    // Off where the page shows the way back on its own.
    resetHint?: boolean;
  } = $props();

  let certificateFile = $state("");
  let keyFile = $state("");

  async function read(event: Event, into: "certificate_pem" | "key_pem") {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (into === "certificate_pem") certificateFile = file?.name ?? "";
    else keyFile = file?.name ?? "";
    choice[into] = file ? await file.text() : "";
  }
</script>

<fieldset class="checks modes">
  <legend class="visually-hidden">Certificate</legend>
  {#each MODES as option (option.mode)}
    <label class="check">
      <input type="radio" name="tls-mode" value={option.mode} bind:group={choice.mode} />
      <span>
        <span class="check-title">{option.name}</span>
        <span class="small muted">{option.about}</span>
      </span>
    </label>
  {/each}
</fieldset>

{#if choice.mode === "own"}
  <div class="grid">
    <div class="field">
      <label for="tls-certificate">Certificate</label>
      <input id="tls-certificate" class="input" type="file" accept=".pem,.crt,.cer"
        required={!uploaded} onchange={(event) => read(event, "certificate_pem")} />
      <span class="hint">For {host}, with any intermediate certificates after it.</span>
    </div>
    <div class="field">
      <label for="tls-key">Private key</label>
      <input id="tls-key" class="input" type="file" accept=".pem,.key"
        required={!uploaded || !!certificateFile} onchange={(event) => read(event, "key_pem")} />
      <span class="hint">Unencrypted, in PEM form. It stays on this server.</span>
    </div>
  </div>
  {#if uploaded && !certificateFile && !keyFile}
    <p class="small muted">
      Saved: {uploaded.subject}, from {uploaded.issuer}. Pick new files to replace it.
    </p>
  {/if}
{:else if choice.mode === "acme"}
  <div class="field">
    <label for="tls-email">Email for expiry notices (optional)</label>
    <input id="tls-email" class="input" type="email" autocomplete="email" bind:value={choice.acme_email} />
    <span class="hint">Let's Encrypt writes if renewing fails. Caddy renews on its own.</span>
  </div>
  <p class="alert alert-warning">
    {host} must be reachable from the internet on port 443. If Let's Encrypt can't reach it,
    there's no certificate and Skjald can't be opened{resetHint ? ". Then, on the server, run:" : "."}
  </p>
  {#if resetHint}<Command command={RESET_COMMAND} />{/if}
{/if}

<style>
  .modes {
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
</style>
