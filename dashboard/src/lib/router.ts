import { writable } from "svelte/store";

/**
 * Hash-based routing. Not history-mode — FastAPI's StaticFiles serves
 * index.html at / but won't serve it for /configuration, so a hard
 * refresh on /configuration would 404. Hashes sidestep that: the
 * server only ever sees /, and window.location.hash is purely
 * client-side.
 */

export type Route =
  | "overview"
  | "configuration"
  | "history"
  | "personality"
  | "login";

const ROUTES: Route[] = ["overview", "configuration", "history", "personality", "login"];

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return ROUTES.includes(hash as Route) ? (hash as Route) : "overview";
}

export const route = writable<Route>(parseHash());

window.addEventListener("hashchange", () => route.set(parseHash()));

export function navigate(to: Route): void {
  window.location.hash = `#/${to}`;
}
