"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Compass, Sparkles, RotateCcw } from "lucide-react";
import type {
  AgentState,
  ChatApiResponse,
  ChatMessage,
  InputMode,
  InterruptPayload,
} from "@/lib/types";
import { resumeChat, sendChatMessage } from "@/lib/api";
import { Message, TypingIndicator } from "./Message";
import { Composer } from "./Composer";
import { FollowUpForm } from "./FollowUpForm";
import { StatePanel } from "./StatePanel";
import { LanguageSwitcher } from "./LanguageSwitcher";

const SUGGESTIONS = [
  "Bus to Kandy from Colombo tomorrow at 8am",
  "Cheapest train to Galle next Monday morning",
  "Taxi from airport to Colombo Fort, fare under LKR 5000",
  "මට කොළඹ සිට මහනුවරට යාමට අවශ්‍යයි",
];

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function ChatApp() {
  const [mode, setMode] = useState<InputMode>("english");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<InterruptPayload | null>(null);
  const [language, setLanguage] = useState<string>("en");
  const [state, setState] = useState<AgentState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollerRef.current;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  }, []);

  useEffect(scrollToBottom, [messages.length, busy, pending, scrollToBottom]);

  const appendMessage = (m: ChatMessage) => setMessages((prev) => [...prev, m]);

  const handleApiResult = useCallback((res: ChatApiResponse) => {
    setThreadId(res.thread_id);
    setLanguage(res.language || "en");
    setState(res.state || null);
    if (res.type === "interrupt" && res.interrupt) {
      setPending(res.interrupt);
      appendMessage({
        id: uid(),
        role: "assistant",
        content: res.interrupt.question,
        createdAt: Date.now(),
      });
    } else {
      setPending(null);
      if (res.response) {
        appendMessage({
          id: uid(),
          role: "assistant",
          content: res.response,
          createdAt: Date.now(),
        });
      }
    }
  }, []);

  const sendUserText = useCallback(
    async (text: string) => {
      if (!text.trim() || busy) return;
      setError(null);
      appendMessage({
        id: uid(),
        role: "user",
        content: text,
        createdAt: Date.now(),
      });
      setBusy(true);
      try {
        const res = await sendChatMessage(text, threadId);
        handleApiResult(res);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        appendMessage({
          id: uid(),
          role: "assistant",
          content: `⚠️ ${msg}`,
          createdAt: Date.now(),
        });
      } finally {
        setBusy(false);
      }
    },
    [busy, threadId, handleApiResult],
  );

  const submitFollowUp = useCallback(
    async (updates: Record<string, string>) => {
      if (!threadId || busy) return;
      setError(null);
      const summary = Object.entries(updates)
        .map(([k, v]) => `**${k.replace(/_/g, " ")}**: ${v}`)
        .join("  \n");
      appendMessage({
        id: uid(),
        role: "user",
        content: summary,
        createdAt: Date.now(),
      });
      setBusy(true);
      setPending(null);
      try {
        const res = await resumeChat(threadId, updates);
        handleApiResult(res);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        appendMessage({
          id: uid(),
          role: "assistant",
          content: `⚠️ ${msg}`,
          createdAt: Date.now(),
        });
      } finally {
        setBusy(false);
      }
    },
    [threadId, busy, handleApiResult],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setPending(null);
    setThreadId(null);
    setState(null);
    setError(null);
  }, []);

  const empty = messages.length === 0 && !pending;

  return (
    <div className="mx-auto max-w-4xl w-full px-4 sm:px-6 py-6 flex flex-col gap-4 min-h-screen">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid place-items-center h-10 w-10 rounded-xl bg-gradient-to-br from-brand-500 to-indigo-500 shadow-lg shadow-indigo-500/20">
            <Compass className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base sm:text-lg font-semibold leading-tight tracking-tight">
              SmartMove
            </h1>
            <p className="text-xs text-white/55 leading-tight">
              Agentic transport assistant · English · Singlish · සිංහල
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={reset}
          disabled={busy || (messages.length === 0 && !threadId)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1.5 text-xs text-white/80 transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          New chat
        </button>
      </header>

      <StatePanel state={state} />

      <div
        ref={scrollerRef}
        className="glass rounded-2xl flex-1 min-h-[460px] max-h-[64vh] overflow-y-auto scroll-thin p-5 flex flex-col gap-4"
      >
        {empty ? (
          <EmptyState onPick={sendUserText} />
        ) : (
          messages.map((m) => <Message key={m.id} message={m} />)
        )}
        {busy && <TypingIndicator />}
      </div>

      <div className="flex flex-col gap-2">
        <LanguageSwitcher mode={mode} onChange={setMode} disabled={busy} />
        {pending ? (
          <FollowUpForm
            payload={pending}
            mode={mode}
            language={language}
            disabled={busy}
            onSubmit={submitFollowUp}
          />
        ) : (
          <Composer mode={mode} disabled={busy} onSend={sendUserText} />
        )}
      </div>

      {error && (
        <p className="text-xs text-amber-300/80 px-1">{error}</p>
      )}
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-4 py-10 animate-fade-in">
      <div className="grid place-items-center h-14 w-14 rounded-2xl bg-gradient-to-br from-brand-500 to-indigo-500 shadow-xl shadow-indigo-500/30">
        <Sparkles className="h-7 w-7 text-white" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">How can I help with your trip?</h2>
        <p className="text-sm text-white/55 max-w-md">
          I plan routes, fares and schedules across Sri Lanka using a Neo4j
          knowledge graph. I&apos;ll ask you for missing details when needed.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-2xl">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="text-left rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-3 text-sm transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
