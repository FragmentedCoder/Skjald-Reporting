// The report styles API (backend/app/styles/routes.py) and customers' report backgrounds
// (backend/app/background_routes.py): what they send and take.

import { api } from "#lib/api.js";
import type { Margins, StyleContent } from "./resolve";

export interface StyleSummary {
  id: number;
  name: string;
  customer_id: number | null;
  customer_name: string | null;
  based_on: number | null;
  is_default: boolean;
  version: number;
  updated_at: string;
  updated_by: string | null;
}

export interface StyleAsset {
  sha256: string;
  content_type: string;
  width: number;
  height: number;
}

export interface Style extends StyleSummary {
  content: StyleContent;
  /** The styles this one stacks on, bottom first, above the Skjald default. */
  below: StyleContent[];
  assets: StyleAsset[];
  problems: string[];
}

export interface StyleVersion {
  number: number;
  saved_at: string;
  saved_by: string | null;
}

export interface Upload {
  status: "ready" | "converting" | "failed";
  message: string;
  pages: string[];
  upload: number | null;
}

export interface CustomerStyles {
  default_style_id: number | null;
  allowed: number[];
  choices: StyleSummary[];
  company_default: number | null;
}

export interface Background {
  status: "ready" | "converting" | "failed";
  message: string;
  pages: number;
  margins: Margins;
  uploaded_at: string;
  uploaded_by: string | null;
}

export const stylesApi = {
  list: () => api<StyleSummary[]>("GET", "/styles"),
  get: (id: number) => api<Style>("GET", `/styles/${id}`),
  create: (name: string, customerId: number | null, basedOn: number | null) =>
    api<Style>("POST", "/styles", { name, customer_id: customerId, based_on: basedOn }),
  update: (id: number, body: { name: string; based_on: number | null; content: StyleContent; version: number }) =>
    api<Style>("PUT", `/styles/${id}`, body),
  remove: (id: number) => api<void>("DELETE", `/styles/${id}`),
  setCompanyDefault: (styleId: number | null) => api<StyleSummary[]>("PUT", "/styles/company-default", { style_id: styleId }),
  versions: (id: number) => api<StyleVersion[]>("GET", `/styles/${id}/versions`),
  version: (id: number, number: number) => api<StyleContent>("GET", `/styles/${id}/versions/${number}`),
  upload: (id: number, file: Blob, use: "artwork" | "image") => api<Upload>("POST", `/styles/${id}/assets?use=${use}`, file),
  uploadStatus: (id: number, upload: number) => api<Upload>("GET", `/styles/${id}/uploads/${upload}`),
  assetUrl: (id: number, sha: string) => `/api/styles/${id}/assets/${sha}`,
  customerStyles: (customerId: number) => api<CustomerStyles>("GET", `/customers/${customerId}/report-style`),
  setCustomerStyles: (customerId: number, defaultStyleId: number | null, allowed: number[]) =>
    api<CustomerStyles>("PUT", `/customers/${customerId}/report-style`, { default_style_id: defaultStyleId, allowed }),
};

export const backgroundApi = {
  get: (customerId: number) => api<Background>("GET", `/customers/${customerId}/background`),
  upload: (customerId: number, file: Blob) => api<Background>("PUT", `/customers/${customerId}/background`, file),
  margins: (customerId: number, margins: Margins) => api<Background>("PATCH", `/customers/${customerId}/background`, margins),
  remove: (customerId: number) => api<void>("DELETE", `/customers/${customerId}/background`),
  pageUrl: (customerId: number, page: number, version: string) => `/api/customers/${customerId}/background/pages/${page}?v=${encodeURIComponent(version)}`,
};

/** Waits for the renderer to convert an upload: polls gently, for at most two minutes. */
export async function whenConverted<T extends { status: string }>(check: () => Promise<T>, everyMs = 1500, giveUpMs = 120_000): Promise<T> {
  const until = Date.now() + giveUpMs;
  for (;;) {
    const found = await check();
    if (found.status !== "converting" || Date.now() > until) return found;
    await new Promise((resolve) => setTimeout(resolve, everyMs));
  }
}
