import { writable, get } from "svelte/store";

/**
 * Token lives in memory only. No localStorage, no sessionStorage, no
 * cookies — an XSS payload can read those. If the tab reloads, the
 * user logs in again. Annoying but safe. The JWT has a 30-day TTL so
 * at least they don't need to log in every few minutes.
 */
export const token = writable<string | null>(null);
export const customerId = writable<string | null>(null);

export function setSession(tok: string, cid: string): void {
  token.set(tok);
  customerId.set(cid);
}

export function clearSession(): void {
  token.set(null);
  customerId.set(null);
}

export function getToken(): string | null {
  return get(token);
}

export function isAuthenticated(): boolean {
  return get(token) !== null;
}
