/**
 * Typed API client. Every call to /v1/* goes through here — no raw
 * fetch() scattered across components. This is where token injection,
 * 401 handling, and error-shape parsing live.
 */
import { getToken, clearSession, setSession } from "./auth";
import { navigate } from "./router";
import type {
  ActivitySummary,
  ConversationHistoryResponse,
  ConversationListResponse,
  LoginRequest,
  LoginResponse,
  Notification,
  Settings,
  SpecialistStatus,
} from "./types";

/** API error envelope matches src/api/errors.py: {type, detail}. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public type: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;

  const res = await fetch(`/v1${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    // Token expired, revoked, or we never had one. Drop session and
    // punt to login. The caller's promise still rejects so components
    // can stop their loading spinners.
    clearSession();
    navigate("login");
    throw new ApiError(401, "unauthorized", "Session expired");
  }

  if (!res.ok) {
    // Best effort at the {type, detail} shape; fall back gracefully.
    let type = "error";
    let detail = res.statusText;
    try {
      const j = await res.json();
      type = j.type ?? type;
      detail = j.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, type, detail);
  }

  // 204 or empty body.
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- Auth ---------------------------------------------------------------

export async function login(creds: LoginRequest): Promise<LoginResponse> {
  // Unauthenticated: token not attached (there isn't one yet), and
  // we want 401 to surface to the login form, not redirect.
  const res = await fetch("/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(creds),
  });
  if (!res.ok) {
    let detail = "Login failed";
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, "unauthorized", detail);
  }
  const body = (await res.json()) as LoginResponse;
  setSession(body.token, body.customer_id);
  return body;
}

// --- Settings -----------------------------------------------------------

export const getSettings = () => request<Settings>("GET", "/settings");
export const putSettings = (s: Settings) => request<Settings>("PUT", "/settings", s);

// --- Conversations ------------------------------------------------------

export const listConversations = (limit = 50, offset = 0) =>
  request<ConversationListResponse>("GET", `/conversations?limit=${limit}&offset=${offset}`);

export const getConversationMessages = (id: string) =>
  request<ConversationHistoryResponse>("GET", `/conversations/${encodeURIComponent(id)}/messages`);

// --- Notifications ------------------------------------------------------

export const getNotifications = () => request<Notification[]>("GET", "/notifications");

// --- Not-yet-built endpoints --------------------------------------------
// TODO(backend): wire these to real endpoints. Placeholder data until then.

export async function getActivitySummary(): Promise<ActivitySummary> {
  // TODO: GET /v1/activity/today
  return { messages: 0, delegations: 0, proactive_triggers: 0 };
}

export async function getSpecialistStatus(): Promise<SpecialistStatus[]> {
  // TODO: GET /v1/specialists
  return [
    { name: "scheduling", operational: true },
    { name: "finance", operational: true },
    { name: "social_media", operational: false },
  ];
}
