import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";

// Moved into the Database page.
export function load() {
  redirect(307, resolve("/(app)/database/variables"));
}
