<script lang="ts" module>
  export type UserAction = "reset-password" | "reset-mfa" | "sign-out" | "disable" | "enable" | "unlock";
</script>

<script lang="ts">
  // What an administrator can do to someone else's account, with the confirmation
  // each needs. Used by the users list's row menus and by the user's own page.
  import { api, ApiError } from "$lib/api";
  import {
    newPasswordChoice,
    passwordFields,
    type PasswordResult,
    type UserDetail,
    type UserSummary,
  } from "$lib/admin";
  import { toast } from "$lib/toast.svelte";
  import Dialog from "./Dialog.svelte";
  import PasswordChoiceFields from "./PasswordChoiceFields.svelte";
  import TemporaryPasswordNotice from "./TemporaryPasswordNotice.svelte";

  let { onChanged }: { onChanged: (user: UserDetail) => void } = $props();

  const CONFIRM: Partial<Record<UserAction, { title: string; explain: (name: string) => string; button: string }>> = {
    "reset-password": {
      title: "Reset password",
      explain: (name) => `${name} gets a new password, and every session they have ends.`,
      button: "Reset password",
    },
    "reset-mfa": {
      title: "Reset multifactor",
      explain: (name) =>
        `This removes ${name}'s authenticator apps, passkeys and recovery codes, for a lost phone or key. They set up multifactor again at their next sign-in, and every session they have ends.`,
      button: "Reset multifactor",
    },
    "sign-out": {
      title: "Sign out everywhere",
      explain: (name) => `Every session ${name} has ends now. They can sign in again.`,
      button: "Sign out everywhere",
    },
    disable: {
      title: "Disable account",
      explain: (name) =>
        `${name} is signed out everywhere at once and can't sign in until the account is enabled again. Nothing they made is removed.`,
      button: "Disable account",
    },
  };

  const DONE: Record<UserAction, (name: string) => string> = {
    "reset-password": (name) => `${name}'s password is set. Their sessions have ended.`,
    "reset-mfa": (name) => `${name} sets up multifactor again at their next sign-in.`,
    "sign-out": (name) => `${name} is signed out everywhere.`,
    disable: (name) => `${name} is disabled and signed out everywhere.`,
    enable: (name) => `${name} can sign in again.`,
    unlock: (name) => `${name} is unlocked.`,
  };

  let target = $state<UserSummary | null>(null);
  let action = $state<UserAction | null>(null);
  let open = $state(false);
  let choice = $state(newPasswordChoice());
  let error = $state<string | null>(null);
  let busy = $state(false);
  let issued = $state<PasswordResult | null>(null);
  let issuedOpen = $state(false);

  const text = $derived(action ? CONFIRM[action] : undefined);

  /** Start an action: ask first when it needs confirming, else do it now. */
  export function start(next: UserAction, user: UserSummary): void {
    target = user;
    action = next;
    error = null;
    choice = newPasswordChoice();
    if (CONFIRM[next]) open = true;
    else void perform();
  }

  // Returns the changed user, and whether a dialog already shows the outcome.
  async function request(user: UserSummary, what: UserAction): Promise<[UserDetail, boolean]> {
    const path = `/admin/users/${user.id}`;
    switch (what) {
      case "reset-password": {
        const fields = passwordFields(choice);
        if (typeof fields === "string") throw new ApiError(400, fields);
        const result = await api<PasswordResult>("POST", `${path}/reset-password`, fields);
        issued = result.temporary_password ? result : null;
        issuedOpen = issued !== null;
        return [result.user, issuedOpen];
      }
      case "disable":
      case "enable":
        return [await api<UserDetail>("PATCH", path, { is_active: what === "enable" }), false];
      default:
        return [await api<UserDetail>("POST", `${path}/${what}`), false];
    }
  }

  async function perform(event?: SubmitEvent) {
    event?.preventDefault();
    if (!target || !action) return;
    const [user, what] = [target, action];
    busy = true;
    error = null;
    try {
      const [changed, shown] = await request(user, what);
      open = false;
      onChanged(changed);
      if (!shown) toast(DONE[what](user.display_name), "ok");
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
      if (open) error = message;
      else toast(message, "critical");
    } finally {
      busy = false;
    }
  }
</script>

<Dialog bind:open title={text?.title ?? ""}>
  <form class="stack" onsubmit={perform}>
    {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
    <p>{target && text ? text.explain(target.display_name) : ""}</p>
    {#if action === "reset-password"}
      <PasswordChoiceFields bind:choice />
    {/if}
    <div class="actions">
      <button class="button button-secondary" type="button" onclick={() => (open = false)}>
        Cancel
      </button>
      <button class="button button-primary" type="submit" disabled={busy}>{text?.button}</button>
    </div>
  </form>
</Dialog>

<Dialog bind:open={issuedOpen} title="New one-time password">
  {#if issued?.temporary_password && issued.expires_at}
    <TemporaryPasswordNotice name={issued.user.display_name}
      password={issued.temporary_password} expiresAt={issued.expires_at} />
  {/if}
  {#snippet actions()}
    <button class="button button-primary" type="button" onclick={() => (issuedOpen = false)}>
      Done
    </button>
  {/snippet}
</Dialog>

<style>
  .actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-2);
  }
</style>
