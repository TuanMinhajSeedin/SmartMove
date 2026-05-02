export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
}

export interface AgentState {
  user_query?: string | null;
  user_query_original?: string | null;
  language?: string | null;
  intent?: string | null;
  origin?: string | null;
  destination?: string | null;
  departure_time?: string | null;
  date?: string | null;
  transport_type?: string | null;
  fare?: string | null;
  extracted_data?: Record<string, unknown> | null;
  missing_fields?: string[] | null;
  cypher_query?: string | null;
  result?: string | null;
  response?: string | null;
  follow_up_question?: string | null;
  [key: string]: unknown;
}

export interface ToggleMeta {
  prompt: string;
  need_value: string;
  input_label: string;
  off_value: string;
}

export interface InterruptPayload {
  kind: string;
  question: string;
  missing_fields: string[];
  labels: Record<string, string>;
  toggleable?: string[];
  toggles?: Record<string, ToggleMeta>;
}

export interface ChatApiResponse {
  thread_id: string;
  type: "message" | "interrupt";
  language: string;
  response?: string;
  interrupt?: InterruptPayload;
  state: AgentState;
}

export type InputMode = "english" | "singlish" | "sinhala";

export const INPUT_MODE_LABEL: Record<InputMode, string> = {
  english: "English",
  singlish: "Singlish → සිංහල",
  sinhala: "සිංහල keyboard",
};
