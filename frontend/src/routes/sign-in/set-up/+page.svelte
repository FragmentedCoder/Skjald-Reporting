<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import KeyRound from "@lucide/svelte/icons/key-round";
  import Smartphone from "@lucide/svelte/icons/smartphone";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import AuthLayout from "$lib/components/AuthLayout.svelte";
  import { browserSupportsWebAuthn, passkeyErrorMessage, registerPasskey } from "$lib/passkeys";
  import { groupSecret, qrPath } from "$lib/qr";
  import {
    sessionEnded,
    settle,
    signOut,
    useSession,
    type SecondFactorResult,
    type SessionInfo,
  } from "$lib/session.svelte";

  type Step = "choose" | "app" | "codes";

  let info = $state<SessionInfo | null>(null);
  let step = $state<Step>("choose");
  let enrolment = $state<{ secret: string; otpauth_uri: string } | null>(null);
  let code = $state("");
  let recoveryCodes = $state<string[]>([]);
  let saved = $state(false);
  let copied = $state(false);
  let error = $state<string | null>(null);
  let busy = $state(false);

  const passkeysWork = browserSupportsWebAuthn();
  const qr = $derived(enrolment ? qrPath(enrolment.otpauth_uri) : null);

  onMount(async () => {
    info = await settle((i) => i?.second_factor === "enrol");
  });

  async function attempt<T>(action: () => Promise<T>): Promise<T | null> {
    busy = true;
    error = null;
    try {
      return await action();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await sessionEnded(e.message);
        return null;
      }
      error = e instanceof ApiError ? e.message : passkeyErrorMessage(e);
      return null;
    } finally {
      busy = false;
    }
  }

  function finished(result: SecondFactorResult | null) {
    if (!result) return;
    useSession(result.session);
    recoveryCodes = result.recovery_codes ?? [];
    step = "codes";
  }

  async function choosePasskey() {
    finished(await attempt(() => registerPasskey("Passkey")));
  }

  async function chooseApp() {
    enrolment = await attempt(() => api("POST", "/auth/mfa/totp/enrol"));
    if (enrolment) step = "app";
  }

  async function confirmApp(event: SubmitEvent) {
    event.preventDefault();
    const result = await attempt(() =>
      api<SecondFactorResult>("POST", "/auth/mfa/totp/confirm", { code }),
    );
    code = "";
    finished(result);
  }

  async function copyCodes() {
    await navigator.clipboard.writeText(recoveryCodes.join("\n"));
    copied = true;
  }

  function downloadCodes() {
    const text = [
      "Skjald recovery codes",
      `For ${info?.user.username ?? ""}. Each code works once.`,
      "",
      ...recoveryCodes,
      "",
    ].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    link.download = "skjald-recovery-codes.txt";
    link.click();
    // Revoking in the same tick can cancel the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }
</script>

<svelte:head><title>Set up your second step · Skjald</title></svelte:head>

{#if info}
  {#if step === "choose"}
    <AuthLayout
      heading="Set up your second step"
      intro="Skjald asks for a second step every time you sign in. Choose how you want to confirm it's you."
    >
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      <div class="options">
        {#if passkeysWork}
          <button class="option" type="button" disabled={busy} onclick={choosePasskey}>
            <KeyRound size={22} aria-hidden="true" />
            <span>
              <span class="option-title">Passkey or security key</span>
              <span class="option-text small muted">
                Your device's fingerprint, face or PIN, or a key such as a YubiKey.
              </span>
            </span>
          </button>
        {/if}
        <button class="option" type="button" disabled={busy} onclick={chooseApp}>
          <Smartphone size={22} aria-hidden="true" />
          <span>
            <span class="option-title">Authenticator app</span>
            <span class="option-text small muted">
              A 6-digit code from an app such as Microsoft Authenticator or Google Authenticator.
            </span>
          </span>
        </button>
      </div>
      {#snippet footer()}
        <button class="link-button" type="button" onclick={signOut}>Sign out</button>
      {/snippet}
    </AuthLayout>
  {:else if step === "app" && enrolment && qr}
    <AuthLayout
      heading="Add Skjald to your app"
      intro="Scan the code with your authenticator app, then enter the 6-digit code it shows."
    >
      <svg
        class="qr"
        viewBox="0 0 {qr.size} {qr.size}"
        role="img"
        aria-label="QR code for your authenticator app"
        shape-rendering="crispEdges"
      >
        <rect width={qr.size} height={qr.size} fill="#FFFFFF" />
        <path d={qr.d} fill="#0F1B2D" />
      </svg>
      <div class="field">
        <span class="small muted">Can't scan it? Enter this key instead:</span>
        <span class="mono secret">{groupSecret(enrolment.secret)}</span>
      </div>
      <form class="stack" onsubmit={confirmApp}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <div class="field">
          <label for="code">6-digit code</label>
          <input
            id="code"
            class="input code"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="7"
            required
            bind:value={code}
          />
        </div>
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Confirm
        </button>
      </form>
      {#snippet footer()}
        <button class="link-button" type="button" onclick={() => (step = "choose")}>Back</button>
        <button class="link-button" type="button" onclick={signOut}>Sign out</button>
      {/snippet}
    </AuthLayout>
  {:else if step === "codes"}
    <AuthLayout
      heading="Save your recovery codes"
      intro="If you lose your phone or key, each code lets you sign in once. They are shown only now."
    >
      <ol class="codes mono">
        {#each recoveryCodes as recoveryCode (recoveryCode)}<li>{recoveryCode}</li>{/each}
      </ol>
      <div class="actions">
        <button class="button button-secondary" type="button" onclick={copyCodes}>
          {copied ? "Copied" : "Copy codes"}
        </button>
        <button class="button button-secondary" type="button" onclick={downloadCodes}>
          Download
        </button>
      </div>
      <label class="confirm">
        <input type="checkbox" bind:checked={saved} />
        <span>I have saved these codes somewhere safe</span>
      </label>
      <button
        class="button button-primary button-block"
        type="button"
        disabled={!saved}
        onclick={() => goto(resolve("/"))}
      >
        Continue
      </button>
    </AuthLayout>
  {/if}
{/if}

<style>
  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .option {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-4);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--text);
    text-align: left;
    font: inherit;
    cursor: pointer;
  }
  .option:hover:not(:disabled) {
    background: var(--surface-subtle);
  }
  .option :global(svg) {
    flex: none; /* keep icons full size beside long descriptions */
  }
  .option-title {
    display: block;
    font: var(--type-label);
  }
  .option-text {
    display: block;
  }
  .qr {
    width: 200px;
    height: 200px;
    align-self: center;
    border-radius: var(--radius-sm);
  }
  .secret {
    /* Wrap only between the groups of four, so each group stays readable. */
    overflow-wrap: normal;
  }
  .codes {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-2) var(--space-4);
    margin: 0;
    padding: var(--space-4);
    padding-left: calc(var(--space-4) + 1.5em);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
  }
  .confirm {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .confirm input {
    width: 18px;
    height: 18px;
    accent-color: var(--link);
  }
</style>
