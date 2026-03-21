// Types mirroring the Pydantic schemas in src/api/schemas.py.
// Keep these in sync by hand for now — generating from OpenAPI would
// be the right long-term move but isn't worth the tooling overhead yet.

export type Priority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type Tone = "professional" | "friendly" | "concise" | "detailed";

// --- Auth ---

export interface LoginRequest {
  customer_id: string;
  secret: string;
}

export interface LoginResponse {
  token: string;
  customer_id: string;
}

// --- Settings (matches src/api/schemas.py::Settings) ---

export interface WorkingHours {
  start: string;
  end: string;
  timezone: string;
}

export interface BriefingSettings {
  enabled: boolean;
  time: string;
}

export interface ProactiveSettings {
  priority_threshold: Priority;
  daily_cap: number;
  idle_nudge_minutes: number;
}

export interface PersonalitySettings {
  tone: Tone;
  language: string;
  name: string;
}

export interface ConnectedServices {
  calendar: boolean;
  n8n: boolean;
}

export interface Settings {
  working_hours: WorkingHours;
  briefing: BriefingSettings;
  proactive: ProactiveSettings;
  personality: PersonalitySettings;
  connected_services: ConnectedServices;
}

// --- Conversations (matches src/api/schemas.py::ConversationListResponse etc) ---

export interface ConversationSummary {
  id: string;
  channel: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

export interface HistoryMessage {
  role: string;
  content: string;
  timestamp: string;
}

export interface ConversationHistoryResponse {
  conversation_id: string;
  customer_id: string;
  messages: HistoryMessage[];
  channel?: string | null;
}

// --- Notifications (matches src/api/schemas.py::NotificationResponse) ---

export interface Notification {
  id: string;
  domain: string;
  trigger_type: string;
  priority: string;
  title: string;
  message: string;
  created_at: string;
}

// --- Contracts for endpoints that don't exist yet --------------------
// TODO(backend): these are wishful — define the API here so the
// dashboard is ready when the backend catches up. Until then, the
// client returns placeholder data.

export interface ActivitySummary {
  // TODO: GET /v1/activity/today → {messages, delegations, proactive_triggers}
  messages: number;
  delegations: number;
  proactive_triggers: number;
}

export interface SpecialistStatus {
  // TODO: GET /v1/specialists → [{name, operational}]
  name: string;
  operational: boolean;
}
