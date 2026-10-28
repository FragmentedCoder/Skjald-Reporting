import { describe, expect, it } from "vitest";
import { changeSigner, nextSigner } from "./blocks";
import type { Signer } from "./types";

describe("signers", () => {
  it("adds the first kind of signer a block doesn't have yet", () => {
    expect(nextSigner([])).toEqual({ role: "technician", label: "Technician", style: "handwritten" });
    expect(nextSigner([{ role: "technician", label: "Technician", style: "handwritten" }]).role).toBe("reviewer");
    const both: Signer[] = [{ role: "technician", label: "T", style: "handwritten" }, { role: "reviewer", label: "R", style: "handwritten" }];
    expect(nextSigner(both)).toEqual({ role: "company", label: "Company seal", style: "stamp" });
  });

  it("changes the label and look with the signer, unless the designer changed them", () => {
    const signer: Signer = { role: "reviewer", label: "Reviewer", style: "handwritten" };
    changeSigner(signer, "company");
    expect(signer).toEqual({ role: "company", label: "Company seal", style: "stamp" });

    const own: Signer = { role: "reviewer", label: "Quality check", style: "stamp" };
    changeSigner(own, "technician");
    expect(own).toEqual({ role: "technician", label: "Quality check", style: "stamp" });
  });
});
