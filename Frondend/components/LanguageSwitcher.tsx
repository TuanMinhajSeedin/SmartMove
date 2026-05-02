"use client";

import { Keyboard, Languages, Type } from "lucide-react";
import type { InputMode } from "@/lib/types";
import { INPUT_MODE_LABEL } from "@/lib/types";

interface Props {
  mode: InputMode;
  onChange: (m: InputMode) => void;
  disabled?: boolean;
}

const ICONS: Record<InputMode, React.ReactNode> = {
  english: <Type className="h-3.5 w-3.5" />,
  singlish: <Languages className="h-3.5 w-3.5" />,
  sinhala: <Keyboard className="h-3.5 w-3.5" />,
};

export function LanguageSwitcher({ mode, onChange, disabled }: Props) {
  const modes = Object.keys(INPUT_MODE_LABEL) as InputMode[];
  return (
    <div className="flex items-center gap-1.5 px-1">
      <span className="text-[11px] uppercase tracking-wider text-white/45 mr-1">
        Input language
      </span>
      <div
        role="radiogroup"
        aria-label="Input language"
        className="inline-flex items-center gap-1 rounded-full bg-white/5 border border-white/10 p-1"
      >
        {modes.map((m) => {
          const active = m === mode;
          return (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => onChange(m)}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors ${
                active
                  ? "bg-brand-500/30 text-white shadow-inner border border-brand-300/30"
                  : "text-white/70 hover:text-white hover:bg-white/5 border border-transparent"
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {ICONS[m]}
              <span>{INPUT_MODE_LABEL[m]}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
