"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User } from "lucide-react";
import type { ChatMessage } from "@/lib/types";

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex w-full gap-3 animate-fade-in ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="grid place-items-center h-8 w-8 shrink-0 rounded-full bg-gradient-to-br from-brand-500 to-indigo-500 shadow-lg shadow-indigo-500/30">
          <Bot className="h-4 w-4 text-white" />
        </div>
      )}
      <div
        className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm border ${
          isUser
            ? "bg-brand-600/30 border-brand-400/30 text-white rounded-br-sm"
            : "bg-white/5 border-white/10 text-white/90 rounded-bl-sm"
        }`}
      >
        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      </div>
      {isUser && (
        <div className="grid place-items-center h-8 w-8 shrink-0 rounded-full bg-white/10 border border-white/10">
          <User className="h-4 w-4 text-white/80" />
        </div>
      )}
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex w-full gap-3 animate-fade-in">
      <div className="grid place-items-center h-8 w-8 rounded-full bg-gradient-to-br from-brand-500 to-indigo-500">
        <Bot className="h-4 w-4 text-white" />
      </div>
      <div className="rounded-2xl px-4 py-3 bg-white/5 border border-white/10 flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-white/60 animate-pulse-soft" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/60 animate-pulse-soft [animation-delay:.2s]" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/60 animate-pulse-soft [animation-delay:.4s]" />
      </div>
    </div>
  );
}
