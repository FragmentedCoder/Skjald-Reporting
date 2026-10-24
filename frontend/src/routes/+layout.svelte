<script lang="ts">
  import "#lib/styles/app.css";
  import { onMount, type Snippet } from "svelte";
  import StepUpDialog from "#lib/components/StepUpDialog.svelte";
  import Toaster from "#lib/components/Toaster.svelte";
  import { branding, loadBranding } from "#lib/branding.svelte.js";
  import { applyColours, effectiveColours } from "#lib/colours.js";
  import { session } from "#lib/session.svelte.js";

  let { children }: { children: Snippet } = $props();

  // Bumped when the device switches between light and dark.
  let deviceMode = $state(0);

  onMount(() => {
    void loadBranding();
    const dark = window.matchMedia("(prefers-color-scheme: dark)");
    const changed = () => (deviceMode += 1);
    dark.addEventListener("change", changed);
    return () => dark.removeEventListener("change", changed);
  });

  // The colours follow the site, the person's choice and the light or dark mode.
  $effect(() => {
    void deviceMode;
    void session.current?.user.theme;
    applyColours(effectiveColours(branding.current, session.current?.user.colours));
  });
</script>

{@render children()}

<StepUpDialog />
<Toaster />
