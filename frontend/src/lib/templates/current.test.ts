import { describe, expect, it } from "vitest";
import { withCurrent } from "./current";
import { sampleContext } from "./preview";

describe("withCurrent", () => {
  it("puts current values in place of the examples, and says which", () => {
    const sample = sampleContext({ customer: { agreement: "Gold" } });
    const { values, live } = withCurrent(sample, {
      "customer.name": "Havbryg A/S", "customer.cvr": null, "author.middle_name": "", "customer.custom.agreement": "Silver",
    });
    expect(values.customer.name).toBe("Havbryg A/S");
    expect(values.customer.cvr).toBe(sample.customer.cvr);
    expect(values.customer.custom).toEqual({ agreement: "Silver" });
    expect([...live]).toEqual(["customer.name", "customer.custom.agreement"]);
  });

  it("leaves the sample context as it was", () => {
    const sample = sampleContext({ customer: { agreement: "Gold" } });
    withCurrent(sample, { "customer.name": "Havbryg A/S", "customer.custom.agreement": "Silver" });
    expect(sample.customer.name).toBe("Fjordvik Logistik A/S");
    expect(sample.customer.custom).toEqual({ agreement: "Gold" });
  });
});
