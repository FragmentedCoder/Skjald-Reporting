import { ApiError } from "./api";

// Step-up: some changes need the person to prove it's them again, even though
// they're signed in. The server refuses with reason "step_up_required"; the
// dialog (StepUpDialog, in the root layout) asks, and the change is tried again.

// `why` is what the dialog says it's asking for, when it isn't to change something.
export const stepUp = $state<{ open: boolean; why: string | null }>({ open: false, why: null });

let settleStepUp: ((confirmed: boolean) => void) | null = null;

function ask(why: string | null): Promise<boolean> {
  settleStepUp?.(false);
  stepUp.why = why;
  stepUp.open = true;
  return new Promise((done) => (settleStepUp = done));
}

/** Called by the dialog when the person confirmed, or gave up. */
export function finishStepUp(confirmed: boolean): void {
  stepUp.open = false;
  settleStepUp?.(confirmed);
  settleStepUp = null;
}

/**
 * Run a change; if the server wants a fresh confirmation, ask for it and run it again.
 * `why` takes the place of the dialog's own words, for what isn't a change (seeing a secret).
 */
export async function withStepUp<T>(change: () => Promise<T>, why: string | null = null): Promise<T> {
  try {
    return await change();
  } catch (error) {
    if (!(error instanceof ApiError && error.reason === "step_up_required")) throw error;
    if (!(await ask(why))) throw new ApiError(403, "Nothing was changed.", "step_up_cancelled");
    return await change();
  }
}
