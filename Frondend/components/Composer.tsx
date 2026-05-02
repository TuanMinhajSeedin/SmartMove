"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Eraser, Delete } from "lucide-react";
import type { InputMode } from "@/lib/types";
import { singlishToSinhala } from "@/lib/api";
import { SinhalaKeyboard } from "./SinhalaKeyboard";

interface Props {
  mode: InputMode;
  disabled?: boolean;
  onSend: (text: string) => void;
}

export function Composer({ mode, disabled, onSend }: Props) {
  const [english, setEnglish] = useState("");
  const [singlish, setSinglish] = useState("");
  const [singlishPreview, setSinglishPreview] = useState("");
  const [sinhala, setSinhala] = useState("");
  const [converting, setConverting] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (mode !== "singlish") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!singlish.trim()) {
      setSinglishPreview("");
      return;
    }
    setConverting(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const out = await singlishToSinhala(singlish.trim());
        setSinglishPreview(out.sinhala || "");
      } catch {
        setSinglishPreview("");
      } finally {
        setConverting(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [singlish, mode]);

  const submit = () => {
    if (disabled) return;
    if (mode === "english") {
      const t = english.trim();
      if (!t) return;
      onSend(t);
      setEnglish("");
    } else if (mode === "singlish") {
      const t = (singlishPreview || singlish).trim();
      if (!t) return;
      onSend(t);
      setSinglish("");
      setSinglishPreview("");
    } else {
      const t = sinhala.trim();
      if (!t) return;
      onSend(t);
      setSinhala("");
    }
  };

  const onEnglishKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  if (mode === "english") {
    return (
      <div className="glass rounded-2xl p-3 flex items-end gap-2">
        <textarea
          ref={taRef}
          rows={1}
          value={english}
          onChange={(e) => {
            setEnglish(e.target.value);
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
          }}
          onKeyDown={onEnglishKey}
          disabled={disabled}
          placeholder='Ask about routes — e.g. "Bus to Kandy from Colombo tomorrow at 8am"'
          className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-white/40 px-2 py-2 max-h-40"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !english.trim()}
          className="grid place-items-center h-10 w-10 rounded-xl bg-brand-500 hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-lg shadow-brand-600/30"
          title="Send"
        >
          <Send className="h-4 w-4 text-white" />
        </button>
      </div>
    );
  }

  if (mode === "singlish") {
    return (
      <div className="glass rounded-2xl p-3 flex flex-col gap-2">
        <textarea
          rows={2}
          value={singlish}
          onChange={(e) => setSinglish(e.target.value)}
          disabled={disabled}
          placeholder="Singlish (romanized Sinhala). Example: mata kandy yanna one"
          className="resize-none bg-transparent outline-none text-sm placeholder:text-white/40 px-2 py-2 min-h-[64px]"
        />
        <div className="flex items-center justify-between gap-2 px-1">
          <div className="flex-1 text-[13px] min-h-[1.5rem] text-white/85">
            <span className="text-[11px] uppercase tracking-wider text-white/40 mr-2">
              සිංහල
            </span>
            {converting ? (
              <span className="text-white/50 italic">converting…</span>
            ) : (
              singlishPreview || <span className="text-white/40">—</span>
            )}
          </div>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !(singlishPreview || singlish).trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-2 text-sm text-white shadow-lg shadow-brand-600/30 transition-colors"
          >
            <Send className="h-4 w-4" /> Send
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl p-3 flex flex-col gap-2">
      <textarea
        rows={2}
        value={sinhala}
        onChange={(e) => setSinhala(e.target.value)}
        disabled={disabled}
        placeholder="සිංහල — type or use the on-screen keyboard"
        className="resize-none bg-transparent outline-none text-sm placeholder:text-white/40 px-2 py-2 min-h-[64px]"
      />
      <div className="flex flex-wrap items-center gap-2 px-1">
        <SinhalaKeyboard onChar={(ch) => setSinhala((s) => s + ch)} />
        <button
          type="button"
          onClick={() => setSinhala((s) => s.slice(0, -1))}
          className="inline-flex items-center gap-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-2 text-xs text-white/80 transition-colors"
        >
          <Delete className="h-3.5 w-3.5" /> Backspace
        </button>
        <button
          type="button"
          onClick={() => setSinhala("")}
          className="inline-flex items-center gap-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 px-3 py-2 text-xs text-white/80 transition-colors"
        >
          <Eraser className="h-3.5 w-3.5" /> Clear
        </button>
        <div className="flex-1" />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !sinhala.trim()}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-2 text-sm text-white shadow-lg shadow-brand-600/30 transition-colors"
        >
          <Send className="h-4 w-4" /> Send
        </button>
      </div>
    </div>
  );
}
