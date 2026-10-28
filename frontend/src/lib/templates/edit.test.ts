import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import { check } from "./checks";
import { expressionsOf, freeKey, keyFrom, newQuestion, renameKey, usage } from "./edit";
import { questionsOf, type TemplateContent } from "./types";

const sample = () => structuredClone(incident) as unknown as TemplateContent;

describe("renaming a variable", () => {
  it("changes every rule and text that reads it, and nothing in quotes", () => {
    const content = sample();
    content.layout.push({ id: "b_quoted", kind: "heading", visible_when: null, text: 'Literally "answers.cvss": {{ "answers.cvss" }}' });
    const renamed = renameKey(content, "cvss", "cvss_score");
    const exprs = expressionsOf(renamed).join("\n");
    // Only the quoted one is left.
    expect(exprs.replaceAll('"answers.cvss"', "")).not.toMatch(/answers\.cvss\b(?!_score)/);
    expect(exprs).toContain("answers.cvss_score >= 9.0");
    expect(exprs).toContain("format_number(answers.cvss_score, 1)");
    expect(questionsOf(renamed).find((q) => q.id === "q_cvss")?.key).toBe("cvss_score");
    const heading = renamed.layout.find((b) => b.id === "b_quoted");
    expect(heading && "text" in heading && heading.text).toBe('Literally "answers.cvss": {{"answers.cvss"}}');
    expect(check(renamed)).toEqual([]);
  });

  it("moves the names inside a question with it", () => {
    const renamed = renameKey(sample(), "credentials", "portal_password");
    const exprs = expressionsOf(renamed);
    expect(exprs).toContain("answers.portal_password.filled");
    expect(exprs).toContain("answers.portal_password.printed");
    expect(check(renamed)).toEqual([]);
  });

  it("leaves the original untouched", () => {
    const content = sample();
    renameKey(content, "cvss", "score");
    expect(questionsOf(content).find((q) => q.id === "q_cvss")?.key).toBe("cvss");
  });
});

describe("where a question is used", () => {
  it("counts the blocks that print it and the expressions that read it", () => {
    const content = sample();
    const find = (id: string) => questionsOf(content).find((q) => q.id === id)!;
    expect(usage(content, find("q_attackers")).blocks.map((b) => b.id)).toEqual(["b_table"]);
    expect(usage(content, find("q_cvss"))).toMatchObject({ blocks: [], expressions: 3 });
    expect(usage(content, find("q_credentials")).expressions).toBe(3);
  });
});

describe("new questions", () => {
  it("get a free variable name and their type's settings", () => {
    const content = sample();
    const a = newQuestion("number", content);
    expect(a.key).toBe("number");
    expect(a.settings).toEqual({ whole: false, min: null, max: null, decimals: 1, unit: "" });
    content.form[0].questions.push(a);
    expect(newQuestion("number", content).key).toBe("number_2");
    expect(newQuestion("heading", content).key).toBeNull();
    expect(a.id).toMatch(/^q_[a-z0-9]{8}$/);
  });

  it("names made from labels", () => {
    expect(keyFrom("Highest CVSS score")).toBe("highest_cvss_score");
    expect(keyFrom("Æblegrød på øen")).toBe("aeblegroed_paa_oeen");
    expect(keyFrom("3 things!")).toBe("things");
    expect(keyFrom("!!!")).toBe("answer");
    expect(freeKey("ip", ["ip", "ip_2"])).toBe("ip_3");
  });
});
