<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import KeyRound from "@lucide/svelte/icons/key-round";
  import LockOpen from "@lucide/svelte/icons/lock-open";
  import LogOut from "@lucide/svelte/icons/log-out";
  import Pencil from "@lucide/svelte/icons/pencil";
  import ShieldOff from "@lucide/svelte/icons/shield-off";
  import UserCheck from "@lucide/svelte/icons/user-check";
  import UserPen from "@lucide/svelte/icons/user-pen";
  import UserPlus from "@lucide/svelte/icons/user-plus";
  import UserX from "@lucide/svelte/icons/user-x";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import { userStatus, type UserDetail, type UserSummary } from "$lib/admin";
  import { pageTitle } from "$lib/branding.svelte";
  import Avatar from "$lib/components/Avatar.svelte";
  import Pill from "$lib/components/Pill.svelte";
  import RowMenu, { type MenuItem } from "$lib/components/RowMenu.svelte";
  import UserActions from "$lib/components/UserActions.svelte";
  import { dateTime } from "$lib/format";
  import { roleName } from "$lib/roles";
  import { session } from "$lib/session.svelte";

  let users = $state<UserSummary[] | null>(null);
  let error = $state<string | null>(null);
  let actions: UserActions;

  onMount(async () => {
    try {
      users = await api<UserSummary[]>("GET", "/admin/users");
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The users could not be loaded.";
    }
  });

  function changed(user: UserDetail) {
    if (!users) return;
    const index = users.findIndex((u) => u.id === user.id);
    if (index >= 0) users[index] = user;
  }

  function open(user: UserSummary) {
    void goto(resolve("/admin/users/[id]", { id: String(user.id) }));
  }

  function menu(user: UserSummary): MenuItem[] {
    const items: MenuItem[] = [{ label: "Edit user", icon: Pencil, run: () => open(user) }];
    if (user.id === session.current?.user.id) {
      items.push({ label: "Your account", icon: UserPen, run: () => goto(resolve("/account")) });
      return items;
    }
    items.push({ label: "Reset password…", icon: KeyRound, run: () => actions.start("reset-password", user) });
    if (user.second_factors) {
      items.push({ label: "Reset multifactor…", icon: ShieldOff, run: () => actions.start("reset-mfa", user) });
    }
    items.push({ label: "Sign out everywhere…", icon: LogOut, run: () => actions.start("sign-out", user) });
    if (user.locked) items.push({ label: "Unlock", icon: LockOpen, run: () => actions.start("unlock", user) });
    if (!user.is_break_glass) {
      items.push(
        user.is_active
          ? { label: "Disable account…", icon: UserX, run: () => actions.start("disable", user), danger: true }
          : { label: "Enable account", icon: UserCheck, run: () => actions.start("enable", user) },
      );
    }
    return items;
  }
</script>

<svelte:head><title>{pageTitle("Users · Admin")}</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Users</h1>
    <p class="small muted">Everyone who can sign in, and what their roles let them do.</p>
  </div>
  <a class="button button-primary" href={resolve("/admin/users/new")}>
    <UserPlus size={18} aria-hidden="true" />
    Add user
  </a>
</div>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

{#if users}
  <div class="section table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Name</th><th>Roles</th><th>Status</th><th>Multifactor</th><th>Last sign-in</th>
          <th><span class="visually-hidden">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        {#each users as user (user.id)}
          {@const status = userStatus(user)}
          <tr>
            <td>
              <div class="person">
                <Avatar name={user.display_name} url={user.avatar_url} size={32} />
                <div>
                  <a class="row-link" href={resolve("/admin/users/[id]", { id: String(user.id) })}>
                    {user.display_name}
                  </a>
                  <div class="small muted mono">{user.username}</div>
                </div>
              </div>
            </td>
            <td>
              {user.roles.map(roleName).join(", ") || "No roles"}
              {#if user.is_break_glass}<div><Pill tone="info" text="Break-glass" /></div>{/if}
            </td>
            <td><Pill tone={status.tone} text={status.text} /></td>
            <td>
              {user.second_factors
                ? `${user.second_factors} set up`
                : user.mfa_required ? "Not yet" : "Not required"}
            </td>
            <td>{dateTime(user.last_sign_in_at)}</td>
            <td class="end">
              <RowMenu label="Actions for {user.display_name}" items={menu(user)} />
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<UserActions bind:this={actions} onChanged={changed} />

<style>
  .person {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .end {
    width: 1%;
    text-align: right;
  }
</style>
