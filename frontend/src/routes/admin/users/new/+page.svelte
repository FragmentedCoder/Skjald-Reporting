<script lang="ts">
  import { resolve } from "$app/paths";
  import { api, ApiError } from "$lib/api";
  import {
    newPasswordChoice,
    passwordFields,
    PROFILE_FIELDS,
    type PasswordResult,
    type ProfileForm,
  } from "$lib/admin";
  import { pageTitle } from "$lib/branding.svelte";
  import PasswordChoiceFields from "$lib/components/PasswordChoiceFields.svelte";
  import TemporaryPasswordNotice from "$lib/components/TemporaryPasswordNotice.svelte";
  import { ROLES, type Role } from "$lib/roles";

  let profile = $state<ProfileForm>({
    display_name: "", first_name: "", middle_name: "", last_name: "", job_title: "",
    department: "", email: "", phone: "",
  });
  let username = $state("");
  let roles = $state<Role[]>([]);
  let choice = $state(newPasswordChoice());
  let created = $state<PasswordResult | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    const password = passwordFields(choice);
    if (typeof password === "string") {
      error = password;
      return;
    }
    busy = true;
    error = null;
    try {
      created = await api<PasswordResult>("POST", "/admin/users", {
        ...profile,
        username,
        roles,
        ...password,
      });
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The user could not be added.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle("Add user · Admin")}</title></svelte:head>

<div class="page-header">
  <div>
    <a class="small" href={resolve("/admin/users")}>Users</a>
    <h1 class="title">Add user</h1>
  </div>
</div>

{#if created}
  <section class="section">
    <h2 class="section-title">{created.user.display_name} is added</h2>
    {#if created.temporary_password && created.expires_at}
      <TemporaryPasswordNotice name={created.user.display_name}
        password={created.temporary_password} expiresAt={created.expires_at} />
    {:else}
      <p>
        They sign in with the password you chose{created.user.password_change_required
          ? ", and choose their own straight after"
          : ""}.
      </p>
    {/if}
    <div class="button-row">
      <a class="button button-primary"
        href={resolve("/admin/users/[id]", { id: String(created.user.id) })}>Open user</a>
      <a class="button button-secondary" href={resolve("/admin/users")}>Back to users</a>
    </div>
  </section>
{:else}
  <form class="section stack form-wide" onsubmit={submit}>
    {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
    <div class="field">
      <label for="display-name">Display name</label>
      <input id="display-name" class="input" required maxlength="200"
        bind:value={profile.display_name} />
    </div>
    <div class="field">
      <label for="username">Username</label>
      <input id="username" class="input" autocapitalize="none" spellcheck="false" required
        aria-describedby="username-hint" bind:value={username} />
      <span class="hint" id="username-hint">What they sign in with. No spaces.</span>
    </div>
    <details>
      <summary>Name, title and contact details (optional)</summary>
      <div class="grid">
        {#each PROFILE_FIELDS as field (field.key)}
          <div class="field">
            <label for={field.key}>{field.label}</label>
            <input id={field.key} class="input" type={field.type ?? "text"} autocomplete="off"
              bind:value={profile[field.key]} />
          </div>
        {/each}
      </div>
    </details>
    <fieldset class="checks roles">
      <legend class="check-title">Roles</legend>
      {#each ROLES as option (option.role)}
        <label class="check">
          <input type="checkbox" value={option.role} bind:group={roles} />
          <span>
            <span class="check-title">{option.name}</span>
            <span class="small muted">{option.description}</span>
          </span>
        </label>
      {/each}
    </fieldset>
    <PasswordChoiceFields bind:choice />
    <div class="button-row">
      <button class="button button-primary" type="submit" disabled={busy}>Add user</button>
      <a class="button button-secondary" href={resolve("/admin/users")}>Cancel</a>
    </div>
  </form>
{/if}

<style>
  .form-wide {
    max-width: 640px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  summary {
    font: var(--type-label);
    cursor: pointer;
  }
  .roles {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .roles legend {
    margin-bottom: var(--space-2);
  }
</style>
