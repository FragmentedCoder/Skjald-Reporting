import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { finishStepUp, stepUp, withStepUp } from "./stepUp.svelte";

const stepUpRefusal = () =>
  new ApiError(403, "Confirm it's you again before changing security settings.", "step_up_required");

describe("withStepUp", () => {
  it("asks for confirmation, then tries the change again", async () => {
    const change = vi.fn().mockRejectedValueOnce(stepUpRefusal()).mockResolvedValueOnce("saved");
    const result = withStepUp(change);
    await vi.waitFor(() => expect(stepUp.open).toBe(true));
    finishStepUp(true);
    await expect(result).resolves.toBe("saved");
    expect(change).toHaveBeenCalledTimes(2);
    expect(stepUp.open).toBe(false);
  });

  it("changes nothing when the person gives up", async () => {
    const change = vi.fn().mockRejectedValue(stepUpRefusal());
    const result = withStepUp(change);
    await vi.waitFor(() => expect(stepUp.open).toBe(true));
    finishStepUp(false);
    await expect(result).rejects.toMatchObject({ reason: "step_up_cancelled" });
    expect(change).toHaveBeenCalledTimes(1);
  });

  it("says what it asks for, when told", async () => {
    const look = vi.fn().mockRejectedValueOnce(stepUpRefusal()).mockResolvedValueOnce("shown");
    const result = withStepUp(look, "Skjald checks it's really you before it shows a secret.");
    await vi.waitFor(() => expect(stepUp.open).toBe(true));
    expect(stepUp.why).toBe("Skjald checks it's really you before it shows a secret.");
    finishStepUp(true);
    await expect(result).resolves.toBe("shown");

    // The next one that doesn't say gets the dialog's own words again.
    const change = withStepUp(vi.fn().mockRejectedValueOnce(stepUpRefusal()).mockResolvedValueOnce("saved"));
    await vi.waitFor(() => expect(stepUp.open).toBe(true));
    expect(stepUp.why).toBeNull();
    finishStepUp(true);
    await change;
  });

  it("passes other refusals straight on", async () => {
    const change = vi.fn().mockRejectedValue(new ApiError(400, "Not an address."));
    await expect(withStepUp(change)).rejects.toMatchObject({ status: 400 });
    expect(stepUp.open).toBe(false);
  });
});
