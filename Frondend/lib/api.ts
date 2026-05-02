import type { ChatApiResponse } from "./types";

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Request failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Request failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function sendChatMessage(message: string, threadId?: string | null): Promise<ChatApiResponse> {
  return postJSON<ChatApiResponse>("/api/chat", { message, thread_id: threadId ?? null });
}

export function resumeChat(threadId: string, updates: Record<string, string>): Promise<ChatApiResponse> {
  return postJSON<ChatApiResponse>("/api/resume", { thread_id: threadId, updates });
}

export function singlishToSinhala(text: string): Promise<{ sinhala: string }> {
  return postJSON<{ sinhala: string }>("/api/singlish", { text });
}

export function fetchKeyboard(): Promise<{ rows: string[][] }> {
  return getJSON<{ rows: string[][] }>("/api/keyboard");
}
