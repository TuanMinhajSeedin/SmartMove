"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, AlertCircle, BadgeDollarSign } from "lucide-react";
import type { InputMode, InterruptPayload, ToggleMeta } from "@/lib/types";
import { singlishToSinhala } from "@/lib/api";
import { SinhalaKeyboard } from "./SinhalaKeyboard";

interface Props {
  payload: InterruptPayload;
  mode: InputMode;
  language: string;
  disabled?: boolean;
  onSubmit: (updates: Record<string, string>) => void;
}

const FARE_PRESETS = ["cheapest", "any", "yes"];

export function FollowUpForm({ payload, mode, language, disabled, onSubmit }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const toggleable = useMemo(
    () => new Set(payload.toggleable ?? []),
    [payload.toggleable],
  );
  const toggleMeta: Record<string, ToggleMeta> = payload.toggles ?? {};

  useEffect(() => {
    setValues({});
    setPreviews({});
    setToggles(
      Object.fromEntries((payload.toggleable ?? []).map((f) => [f, false])),
    );
    setError(null);
  }, [payload.question, payload.toggleable]);

  // debounced singlish→sinhala for each text field that's actually visible
  useEffect(() => {
    if (mode !== "singlish") return;
    const handles: Record<string, ReturnType<typeof setTimeout>> = {};
    Object.entries(values).forEach(([k, v]) => {
      // No singlish preview for fare — fare values are normalized English.
      if (k === "fare") return;
      const trimmed = (v || "").trim();
      if (!trimmed) {
        setPreviews((p) => ({ ...p, [k]: "" }));
        return;
      }
      handles[k] = setTimeout(async () => {
        try {
          const out = await singlishToSinhala(trimmed);
          setPreviews((p) => ({ ...p, [k]: out.sinhala }));
        } catch {
          /* ignore */
        }
      }, 350);
    });
    return () => Object.values(handles).forEach(clearTimeout);
  }, [values, mode]);

  const fields = payload.missing_fields ?? [];
  const labels = payload.labels ?? {};

  const setField = (k: string, v: string) =>
    setValues((cur) => ({ ...cur, [k]: v }));

  const submit = () => {
    if (disabled) return;
    const out: Record<string, string> = {};
    for (const f of fields) {
      if (toggleable.has(f)) {
        const enabled = !!toggles[f];
        const meta = toggleMeta[f];
        if (!enabled) {
          out[f] = meta?.off_value ?? "no";
          continue;
        }
        const v = (values[f] || "").trim();
        if (!v) {
          setError(meta?.need_value || `Enter a value for ${labels[f] || f}.`);
          return;
        }
        out[f] = v;
        continue;
      }

      let v = (values[f] || "").trim();
      if (mode === "singlish") {
        v = (previews[f] || v).trim();
      }
      if (!v) {
        setError(`Please fill in ${labels[f] || f}.`);
        return;
      }
      out[f] = v;
    }
    setError(null);
    onSubmit(out);
  };

  return (
    <div className="glass rounded-2xl p-5 animate-fade-in border border-amber-300/20">
      <div className="flex items-start gap-3 mb-4">
        <div className="grid place-items-center h-9 w-9 rounded-xl bg-amber-400/15 border border-amber-300/30 text-amber-300">
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold">Follow-up needed</p>
          <p className="text-sm text-white/75 mt-0.5">{payload.question}</p>
          <p className="text-[11px] text-white/40 mt-1">
            Detected language: <span className="font-mono">{language}</span> · Input mode:{" "}
            <span className="font-mono">{mode}</span>
          </p>
        </div>
      </div>

      <div className="grid gap-3">
        {fields.map((f) => {
          const label = labels[f] || f;

          if (toggleable.has(f)) {
            return (
              <FareToggleField
                key={f}
                fieldKey={f}
                label={label}
                enabled={!!toggles[f]}
                value={values[f] || ""}
                meta={toggleMeta[f]}
                disabled={disabled}
                onToggle={(v) => setToggles((s) => ({ ...s, [f]: v }))}
                onChange={(v) => setField(f, v)}
              />
            );
          }

          const isPlaceField = f === "origin" || f === "destination";
          const placeholder =
            mode === "english"
              ? f === "departure_time"
                ? "e.g. tomorrow 8am, 2026-05-10 09:00"
                : isPlaceField
                ? "City or place name"
                : ""
              : mode === "singlish"
              ? "Romanized Sinhala…"
              : "Type or use keyboard";

          return (
            <div key={f} className="flex flex-col gap-1.5">
              <label className="text-xs uppercase tracking-wider text-white/55">
                {label}
              </label>
              <input
                type="text"
                value={values[f] || ""}
                onChange={(e) => setField(f, e.target.value)}
                placeholder={placeholder}
                disabled={disabled}
                className="rounded-xl bg-white/5 border border-white/10 focus:border-brand-400/60 outline-none px-3 py-2 text-sm placeholder:text-white/40"
              />
              {mode === "singlish" && (
                <p className="text-[11px] text-white/55">
                  සිංහල: <span className="text-white/85">{previews[f] || "—"}</span>
                </p>
              )}
              {mode === "sinhala" && (
                <div className="flex flex-wrap gap-2 mt-1">
                  <SinhalaKeyboard
                    onChar={(ch) => setField(f, (values[f] || "") + ch)}
                    label={`⌨ ${label}`}
                  />
                  <button
                    type="button"
                    onClick={() => setField(f, (values[f] || "").slice(0, -1))}
                    className="rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 py-1 text-[11px]"
                  >
                    ⌫ Backspace
                  </button>
                  <button
                    type="button"
                    onClick={() => setField(f, "")}
                    className="rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 py-1 text-[11px]"
                  >
                    Clear
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <p className="mt-3 text-xs text-amber-300/90 flex items-center gap-1.5">
          <AlertCircle className="h-3.5 w-3.5" /> {error}
        </p>
      )}

      <div className="flex justify-end mt-4">
        <button
          type="button"
          onClick={submit}
          disabled={disabled}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-400 disabled:opacity-40 px-4 py-2 text-sm text-white shadow-lg shadow-brand-600/30 transition-colors"
        >
          <CheckCircle2 className="h-4 w-4" /> Submit details
        </button>
      </div>
    </div>
  );
}

interface FareToggleFieldProps {
  fieldKey: string;
  label: string;
  enabled: boolean;
  value: string;
  meta?: ToggleMeta;
  disabled?: boolean;
  onToggle: (v: boolean) => void;
  onChange: (v: string) => void;
}

function FareToggleField({
  fieldKey,
  label,
  enabled,
  value,
  meta,
  disabled,
  onToggle,
  onChange,
}: FareToggleFieldProps) {
  const promptText = meta?.prompt || "Specify fare or budget preference";
  const inputLabel = meta?.input_label || label;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3.5 flex flex-col gap-2.5">
      <div className="flex items-start gap-3">
        <div className="grid place-items-center h-8 w-8 rounded-lg bg-emerald-400/10 border border-emerald-300/20 text-emerald-300">
          <BadgeDollarSign className="h-4 w-4" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium">{label}</p>
          <p className="text-[11px] text-white/55 mt-0.5">{promptText}</p>
          <p className="text-[10px] text-white/40 mt-0.5">
            Off → submitted as <span className="font-mono">no</span>
          </p>
        </div>
        <ToggleSwitch
          checked={enabled}
          disabled={disabled}
          onChange={onToggle}
          aria-label={promptText}
        />
      </div>

      {enabled && (
        <div className="flex flex-col gap-2 animate-fade-in">
          <label className="text-[11px] uppercase tracking-wider text-white/50">
            {inputLabel}
          </label>
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="e.g. cheapest, max LKR 2000, any"
            disabled={disabled}
            className="rounded-xl bg-white/5 border border-white/10 focus:border-brand-400/60 outline-none px-3 py-2 text-sm placeholder:text-white/40"
          />
          <div className="flex flex-wrap gap-1.5">
            {FARE_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => onChange(p)}
                disabled={disabled}
                className={`rounded-full px-2.5 py-1 text-[11px] border transition-colors ${
                  value.trim().toLowerCase() === p
                    ? "bg-brand-500/25 border-brand-400/40 text-white"
                    : "bg-white/5 border-white/10 text-white/70 hover:bg-white/10"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}

      <input type="hidden" name={fieldKey} value={enabled ? value : (meta?.off_value ?? "no")} readOnly />
    </div>
  );
}

interface ToggleSwitchProps {
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
  "aria-label"?: string;
}

function ToggleSwitch({ checked, disabled, onChange, ...rest }: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={rest["aria-label"]}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked
          ? "bg-brand-500/80 border border-brand-300/40"
          : "bg-white/10 border border-white/15"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}
