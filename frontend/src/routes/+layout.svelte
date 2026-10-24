<script lang="ts">
  import "$lib/styles/app.css";
  import { onMount, type Snippet } from "svelte";
  import StepUpDialog from "$lib/components/StepUpDialog.svelte";
  import Toaster from "$lib/components/Toaster.svelte";
  import { loadBranding } from "$lib/branding.svelte";

  let { children }: { children: Snippet } = $props();

  onMount(() => {
    void loadBranding();
  });
</script>

{@render children()}

<StepUpDialog />
<Toaster />
