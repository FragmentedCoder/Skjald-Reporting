// What a template version holds: the browser's view of backend/app/templates/content.py.
// The server checks the structure on every save; the builder edits it as a whole.

export type Id = string;

export interface RichText {
  type: "doc";
  content: RichNode[];
}

export interface RichNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: RichNode[];
  text?: string;
  marks?: { type: string; attrs?: Record<string, unknown> }[];
}

export interface Settings {
  prefix: string;
  language: "da" | "en";
  signing: "company" | "technician" | "technician_reviewer";
  review: "mandatory" | "optional";
  delivery: ("download" | "email" | "protected_pdf")[];
  styles: ("company" | "customer")[];
  customer_background: boolean;
}

export interface Question {
  id: Id;
  key: string | null;
  type: string;
  label: string;
  help: string;
  required: boolean;
  required_when: string | null;
  visible_when: string | null;
  default: string | null;
  valid_when: string | null;
  valid_message: string;
  value: string | null;
  // Each field type's own settings (fields.ts).
  settings: Record<string, unknown>;
}

export interface Step {
  id: Id;
  title: string;
  help: string;
  visible_when: string | null;
  questions: Question[];
}

interface BlockBase {
  id: Id;
  visible_when: string | null;
}

export interface Cover extends BlockBase {
  kind: "cover";
  title: string;
  subtitle: string;
  facts: { label: string; value: string }[];
  show_logo: boolean;
}

export interface Contents extends BlockBase {
  kind: "toc";
  title: string;
  depth: 1 | 2;
}

export interface Section extends BlockBase {
  kind: "section";
  title: string;
  intro: RichText | null;
  new_page: boolean;
  numbered: boolean;
  landscape: boolean;
  repeat_for: string | null;
  blocks: Block[];
}

export interface Heading extends BlockBase {
  kind: "heading";
  text: string;
}

export interface TextBlock extends BlockBase {
  kind: "text";
  content: RichText;
}

export interface Answer extends BlockBase {
  kind: "answer";
  question: Id | null;
  show_label: boolean;
}

export interface Table extends BlockBase {
  kind: "table";
  question: Id | null;
  caption: string;
  columns: string[] | null;
  empty_text: string;
}

export interface Image extends BlockBase {
  kind: "image";
  source: "template" | "question";
  asset: string | null;
  question: Id | null;
  caption: string;
  width: "full" | "two_thirds" | "half" | "third";
}

export interface Gallery extends BlockBase {
  kind: "gallery";
  question: Id | null;
  caption: string;
  per_row: 2 | 3;
}

export type Tone = "info" | "note" | "warning" | "critical" | "success" | "custom";

export interface Callout extends BlockBase {
  kind: "callout";
  tone: Tone;
  tone_rule: string | null;
  colour: string | null;
  title: string;
  content: RichText;
}

export interface SeveritySummary extends BlockBase {
  kind: "severity_summary";
  question: Id | null;
  column: string | null;
  levels: string[];
  caption: string;
}

export interface Sources extends BlockBase {
  kind: "sources";
  intro: string;
  items: { title: string; link: string }[];
  question: Id | null;
}

export interface Signer {
  role: "technician" | "reviewer" | "company";
  label: string;
  style: "handwritten" | "stamp";
}

export interface Signatures extends BlockBase {
  kind: "signatures";
  signers: Signer[];
  layout: "row" | "stack";
  show_date: boolean;
}

export interface Columns extends BlockBase {
  kind: "columns";
  columns: Block[][];
}

export interface PageBreak extends BlockBase {
  kind: "page_break";
}

export type Block =
  | Cover
  | Contents
  | Section
  | Heading
  | TextBlock
  | Answer
  | Table
  | Image
  | Gallery
  | Callout
  | SeveritySummary
  | Sources
  | Signatures
  | Columns
  | PageBreak;

export type BlockKind = Block["kind"];

export interface TemplateContent {
  schema: 1;
  settings: Settings;
  form: Step[];
  layout: Block[];
  sample: { answers: Record<Id, unknown> };
}

export interface Problem {
  element: string;
  field: string;
  message: string;
}

/** Every question, in form order. */
export function questionsOf(content: TemplateContent): Question[] {
  return content.form.flatMap((step) => step.questions);
}

/** Every block, depth first, the ones inside sections and columns included. */
export function blocksOf(blocks: Block[]): Block[] {
  return blocks.flatMap((block) => {
    if (block.kind === "section") return [block, ...blocksOf(block.blocks)];
    if (block.kind === "columns") return [block, ...block.columns.flatMap(blocksOf)];
    return [block];
  });
}
