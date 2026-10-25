<script lang="ts" module>
  import type { Role } from "#lib/roles.js";

  export interface RoleGroup {
    role: Extract<Role, "technician" | "reviewer">;
    people: { id: number; name: string; note?: string }[];
    empty: string;
  }

  /** How each group is headed and explained. */
  export const ROLE_GROUPS = {
    technician: { title: "Technicians", about: "Do the work and write the reports." },
    reviewer: { title: "Reviewers", about: "Check the work, review and countersign the reports." },
  } as const;
</script>

<script lang="ts">
  import BadgeCheck from "@lucide/svelte/icons/badge-check";
  import PenLine from "@lucide/svelte/icons/pen-line";

  // People listed by what they're there as: the technicians who do the work, and
  // the reviewers who check it. Someone can be in both, on different customers or
  // projects.
  let { groups, compact = false }: { groups: RoleGroup[]; compact?: boolean } = $props();
</script>

<div class="groups" class:compact>
  {#each groups as group (group.role)}
    {@const about = ROLE_GROUPS[group.role]}
    <section class="group {group.role}" aria-label={about.title}>
      <h3 class="group-title">
        {#if group.role === "technician"}<PenLine size={16} aria-hidden="true" />
        {:else}<BadgeCheck size={16} aria-hidden="true" />{/if}
        {about.title}
      </h3>
      {#if !compact}<p class="small muted">{about.about}</p>{/if}
      {#if group.people.length}
        <ul>
          {#each group.people as person (person.id)}
            <li>
              <span class="check-title">{person.name}</span>
              {#if person.note}<span class="small muted">{person.note}</span>{/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="small muted">{group.empty}</p>
      {/if}
    </section>
  {/each}
</div>

<style>
  .groups {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: var(--space-4);
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-left: 3px solid var(--link);
    border-radius: var(--radius-md);
  }
  .group.reviewer {
    border-left-color: var(--accent);
  }
  .compact .group {
    padding: var(--space-2) var(--space-3);
  }
  .group-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font: var(--type-label);
  }
  ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: flex;
    flex-direction: column;
  }
</style>
