// The templates API (backend/app/templates/routes.py): what it sends and takes.

import { api } from "#lib/api.js";
import type { Problem, TemplateContent } from "./types";

export interface DraftSummary {
  revision: number;
  saved_at: string;
  saved_by: string | null;
}

export interface VersionSummary {
  number: number;
  published_at: string;
  published_by: string | null;
  note: string;
  content_sha256: string;
}

export interface Asset {
  sha256: string;
  name: string;
  content_type: string;
  width: number;
  height: number;
  url: string;
}

export interface TemplateSummary {
  id: number;
  uuid: string;
  name: string;
  description: string;
  latest_version: number | null;
  published_at: string | null;
  draft: DraftSummary | null;
  retired: boolean;
  updated_at: string;
}

export interface TemplateDetail extends TemplateSummary {
  versions: VersionSummary[];
  assets: Asset[];
}

export interface DraftOut extends DraftSummary {
  content: TemplateContent;
  problems: Problem[];
}

export interface Saved {
  revision: number;
  saved_at: string;
  problems: Problem[];
}

export interface VersionOut extends VersionSummary {
  content: TemplateContent;
}

export interface Item {
  id: string;
  label: string;
}

export interface Changes {
  questions_added: Item[];
  questions_removed: Item[];
  questions_changed: (Item & { parts: string[] })[];
  blocks_added: Item[];
  blocks_removed: Item[];
  blocks_changed: (Item & { parts: string[] })[];
  settings_changed: string[];
}

const base = (id: number) => `/templates/${id}`;

export const templatesApi = {
  list: () => api<TemplateSummary[]>("GET", "/templates"),
  create: (name: string, description: string) => api<TemplateDetail>("POST", "/templates", { name, description }),
  get: (id: number) => api<TemplateDetail>("GET", base(id)),
  update: (id: number, change: { name?: string; description?: string }) => api<TemplateDetail>("PATCH", base(id), change),
  retire: (id: number) => api<TemplateDetail>("POST", `${base(id)}/retire`),
  restore: (id: number) => api<TemplateDetail>("POST", `${base(id)}/restore`),
  remove: (id: number) => api<void>("DELETE", base(id)),
  copy: (id: number, name: string) => api<TemplateDetail>("POST", `${base(id)}/copy`, { name }),
  draft: (id: number) => api<DraftOut>("GET", `${base(id)}/draft`),
  startDraft: (id: number, fromVersion?: number) =>
    api<DraftOut>("POST", `${base(id)}/draft`, fromVersion === undefined ? {} : { from_version: fromVersion }),
  save: (id: number, content: TemplateContent, revision: number) =>
    api<Saved>("PUT", `${base(id)}/draft`, { content, revision }),
  discard: (id: number) => api<void>("DELETE", `${base(id)}/draft`),
  publish: (id: number, revision: number, note: string) =>
    api<VersionSummary>("POST", `${base(id)}/publish`, { revision, note }),
  version: (id: number, number: number) => api<VersionOut>("GET", `${base(id)}/versions/${number}`),
  changes: (id: number) => api<Changes>("GET", `${base(id)}/changes`),
  upload: (id: number, file: File) =>
    api<Asset>("POST", `${base(id)}/assets?name=${encodeURIComponent(file.name)}`, file),
};
