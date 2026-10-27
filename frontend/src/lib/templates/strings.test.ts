import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import shared from "../../../../shared/templates/strings.json";
import { apply, rules, strings } from "./strings";
import type { TemplateContent } from "./types";

const content = () => structuredClone(incident) as unknown as TemplateContent;

describe("strings and rules", () => {
  it("are gathered as the server gathers them", () => {
    expect(strings(content())).toEqual(shared.strings);
    expect(rules(content())).toEqual(shared.rules);
  });

  it("go back where they came from", () => {
    const template = content();
    expect(apply(template, strings(template), rules(template))).toEqual([]);
    expect(template).toEqual(content());
    const missing = apply(template, { "q_summary/label": "Resumé af hændelsen", "b_cover/facts/0/label": "Rapport", "q_nope/label": "x" }, { "b_attack/visible_when": "true", "q_summary/label": "true" });
    expect(missing).toEqual(["q_nope/label", "q_summary/label"]);
    expect(template.form[0].questions[0].label).toBe("Resumé af hændelsen");
    expect(rules(template)["b_attack/visible_when"]).toBe("true");
  });

  it("leave option values and links alone", () => {
    const template = content();
    expect(apply(template, { "q_attackers/settings/columns/2/settings/options/0/value": "x", "b_srclist/items/0/link": "x" })).toHaveLength(2);
  });
});
