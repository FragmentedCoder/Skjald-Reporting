import { getContext, setContext } from "svelte";
import type { CustomerDetail, ProjectDetail } from "./customers.js";

// What a customer's or a project's layout shares with the pages under it: the
// loaded record, and a way to replace or reload it after a change.

export interface Loaded<T> {
  readonly current: T | null;
  use(found: T): void;
  reload(): Promise<void>;
}

const CUSTOMER = Symbol("customer");
const PROJECT = Symbol("project");

export function shareCustomer(customer: Loaded<CustomerDetail>): void {
  setContext(CUSTOMER, customer);
}

export function sharedCustomer(): Loaded<CustomerDetail> {
  return getContext<Loaded<CustomerDetail>>(CUSTOMER);
}

export function shareProject(project: Loaded<ProjectDetail>): void {
  setContext(PROJECT, project);
}

export function sharedProject(): Loaded<ProjectDetail> {
  return getContext<Loaded<ProjectDetail>>(PROJECT);
}
