"use client";

import { useEffect, useState } from "react";
import { Keyboard, X } from "lucide-react";
import { fetchKeyboard } from "@/lib/api";

interface Props {
  onChar: (ch: string) => void;
  label?: string;
}

const FALLBACK_ROWS: string[][] = [
  ["අ", "ආ", "ඇ", "ඈ", "ඉ", "ඊ", "උ", "ඌ", "එ", "ඒ", "ඔ", "ඕ"],
  ["ක", "ඛ", "ග", "ඝ", "ඞ", "ඟ", "ච", "ඡ", "ජ", "ඣ", "ඤ", "ඥ"],
  ["ට", "ඨ", "ඩ", "ඪ", "ණ", "ත", "ථ", "ද", "ධ", "න"],
  ["ප", "ඵ", "බ", "භ", "ම", "ඹ", "ය", "ර", "ල", "ව"],
  ["ශ", "ෂ", "ස", "හ", "ළ", "ෆ", "ං", "ඃ", "ඳ"],
  ["්", "ා", "ැ", "ෑ", "ි", "ී", "ු", "ූ", "ෘ", "ෲ"],
  ["ෙ", "ේ", "ෛ", "ො", "ෝ", "ෞ"],
];

export function SinhalaKeyboard({ onChar, label = "සිංහල keyboard" }: Props) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<string[][]>(FALLBACK_ROWS);

  useEffect(() => {
    fetchKeyboard()
      .then((d) => setRows(d.rows?.length ? d.rows : FALLBACK_ROWS))
      .catch(() => undefined);
  }, []);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-xs text-white/80 hover:bg-white/10 transition-colors"
      >
        <Keyboard className="h-3.5 w-3.5" /> {label}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-40 grid place-items-end sm:place-items-center bg-black/50 backdrop-blur-sm p-3"
          onClick={() => setOpen(false)}
        >
          <div
            className="glass rounded-2xl p-4 w-full max-w-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold">{label}</p>
              <button
                type="button"
                className="grid place-items-center h-8 w-8 rounded-lg hover:bg-white/10"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-col gap-1.5">
              {rows.map((row, ri) => (
                <div key={ri} className="grid grid-cols-12 gap-1.5">
                  {row.map((ch, ci) => (
                    <button
                      key={`${ri}-${ci}`}
                      type="button"
                      onClick={() => onChar(ch)}
                      className="h-9 rounded-lg bg-white/5 hover:bg-brand-500/30 border border-white/10 text-sm text-white/90 transition-colors"
                    >
                      {ch.trim() ? ch : "·"}
                    </button>
                  ))}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-white/45 mt-3">
              Tap letters to append. Combine consonants with vowel signs to form syllables.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
