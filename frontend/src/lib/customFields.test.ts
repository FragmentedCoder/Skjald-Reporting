import { describe, expect, it } from "vitest";
import { customLabels, customNames, sampleCustom, type CustomField } from "./customFields";
import { catalogue } from "./templates/catalogue";
import { sampleContext } from "./templates/preview";
import type { TemplateContent } from "./templates/types";

function field(applies_to: CustomField["applies_to"], key: string, type: CustomField["type"], more: Partial<CustomField> = {}): CustomField {
  return { id: key.length, applies_to, key, label: key, type, help: "", options: [], position: 0, archived: false, ...more };
}

const FIELDS = [
  field("customer", "agreement", "dropdown", { label: "Support agreement", options: ["Gold", "Silver"] }),
  field("customer", "hours", "number"),
  field("customer", "renewal", "date"),
  field("customer", "old", "text", { archived: true }),
  field("project", "ticket", "text", { label: "Ticket number" }),
];

describe("custom fields", () => {
  it("are read by name, with the types the server gives them", () => {
    expect(customNames(FIELDS)).toEqual({
      "customer.custom.agreement": "string",
      "customer.custom.hours": "double",
      "customer.custom.renewal": "timestamp",
      "project.custom.ticket": "string",
    });
    expect(customLabels(FIELDS)["project.custom.ticket"]).toBe("Ticket number");
  });

  it("have examples for previews", () => {
    expect(sampleCustom(FIELDS, "customer")).toEqual({ agreement: "Gold", hours: 12, renewal: "2027-03-01" });
    const context = sampleContext({ project: sampleCustom(FIELDS, "project") });
    expect(context.project.custom).toEqual({ ticket: "SLA-2026-17" });
    expect(context.customer.custom).toEqual({});
  });

  it("show in the Data tab under their own heading", () => {
    const empty = { settings: {}, form: [], layout: [], sample: { answers: {} } } as unknown as TemplateContent;
    const entries = catalogue(empty, customNames(FIELDS), customLabels(FIELDS));
    expect(entries.find((e) => e.name === "customer.custom.agreement")).toMatchObject({ group: "Customer: custom fields", label: "Support agreement" });
    expect(entries.find((e) => e.name === "project.custom.ticket")?.group).toBe("Project: custom fields");
  });
});
