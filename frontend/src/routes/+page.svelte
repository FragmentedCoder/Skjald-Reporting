<script lang="ts">
  import LogOut from "@lucide/svelte/icons/log-out";
  import { onMount } from "svelte";
  import Mark from "$lib/components/Mark.svelte";
  import { settle, signOut, type Role, type SessionInfo } from "$lib/session.svelte";

  let info = $state<SessionInfo | null>(null);

  const ROLE_NAMES: Record<Role, string> = {
    administrator: "Administrator",
    report_designer: "Report designer",
    technician: "Technician",
    reviewer: "Reviewer",
    auditor: "Auditor",
  };

  onMount(async () => {
    info = await settle("/");
  });
</script>

<svelte:head><title>Skjald</title></svelte:head>

{#if info}
  <header class="bar">
    <div class="brand">
      <Mark size={32} />
      <span class="wordmark">Skjald</span>
    </div>
    <div class="who">
      <span class="small muted">{info.user.display_name}</span>
      <button class="button button-secondary" type="button" onclick={signOut}>
        <LogOut size={16} aria-hidden="true" />
        Sign out
      </button>
    </div>
  </header>
  <main class="content">
    <div class="heading">
      <h1 class="title">Welcome, {info.user.display_name}</h1>
      {#if info.user.roles.length}
        <p class="small muted">{info.user.roles.map((r) => ROLE_NAMES[r]).join(", ")}</p>
      {/if}
    </div>
    <section class="empty">
      <p>The hall is quiet for now.</p>
      <p class="small muted">Customers, projects and reports will appear here.</p>
    </section>
  </main>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-6);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .brand,
  .who {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .wordmark {
    font: var(--type-subheading);
  }
  .content {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 960px;
    margin: 0 auto;
    padding: var(--space-8) var(--space-6);
  }
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .empty {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
  @media (max-width: 480px) {
    .bar,
    .content {
      padding-inline: var(--space-4);
    }
  }
</style>
