import { ApiError, sessionGone } from "#lib/api.js";
import { toast } from "#lib/toast.svelte.js";

/**
 * Does something the reader asked for (a checkout, a release, a new title). A refusal is
 * said in a toast: the server's sentence when it gave one. Returns whether it worked.
 */
export async function attempt(action: () => Promise<unknown>, otherwise: string): Promise<boolean> {
  try {
    await action();
    return true;
  } catch (error) {
    if (!sessionGone(error)) toast(error instanceof ApiError ? error.message : otherwise, "critical");
    return false;
  }
}
