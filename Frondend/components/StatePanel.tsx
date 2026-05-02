"use client";

import { useState } from "react";
import { ChevronDown, Database } from "lucide-react";
import type { AgentState } from "@/lib/types";

const HIGHLIGHT_KEYS = [
  "language",
  "intent",
  "origin",
  "destination",
  "departure_time",
  "date",
  "transport_type",
  "fare",
];

export function StatePanel({ state }: { state: AgentState | null }) {
  const [open, setOpen] = useState(false);
  const has = state && Object.keys(state).length > 0;

  return (
    <div className="glass rounded-2xl">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-sm text-white/80 hover:text-white transition-colors"
      >
        <span className="flex items-center gap-2">
          <Database className="h-4 w-4 text-brand-300" /> Agent state
          {!has && <span className="text-xs text-white/40 ml-1">— empty</span>}
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-3 border-t border-white/5">
          {has ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
                {HIGHLIGHT_KEYS.map((k) => {
                  const v = state?.[k];
                  return (
                    <div
                      key={k}
                      className="rounded-xl bg-white/5 border border-white/5 px-3 py-2"
                    >
                      <p className="text-[10px] uppercase tracking-wider text-white/45">
                        {k.replace(/_/g, " ")}
                      </p>
                      <p className="text-xs text-white/90 truncate">
                        {v == null || v === "" ? (
                          <span className="text-white/35">—</span>
                        ) : (
                          String(v)
                        )}
                      </p>
                    </div>
                  );
                })}
              </div>
              <details className="rounded-xl bg-black/30 border border-white/5">
                <summary className="cursor-pointer text-xs px-3 py-2 text-white/60 hover:text-white">
                  Raw state JSON
                </summary>
                <pre className="text-[11px] text-white/75 px-3 pb-3 overflow-x-auto scroll-thin max-h-72">
                  {JSON.stringify(state, null, 2)}
                </pre>
              </details>
            </>
          ) : (
            <p className="text-xs text-white/50 mt-2">
              The agent state will appear here once you send a message.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
