/**
 * Shared TTS voice settings form for the Super Admin (platform defaults) and
 * Tenant Admin (tenant overrides). Voice options come from the device's real
 * voice list (spec §4 — only voices the browser can actually play), showing
 * name, language, locale, provider and gender when derivable. Includes speed
 * presets (spec §5) and a Preview button that speaks with the CURRENT form
 * values before anything is saved.
 */
import { useMemo, useState } from "react";
import { Spinner } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import { speakWithSettings, useBrowserVoices, voiceGender } from "@/hooks/useSpeech";
import { cn } from "@/lib/utils";
import type { AdminVoiceSettings, VoiceGender } from "@/api/types";

const SPEED_PRESETS: { value: number; label: string }[] = [
  { value: 0.5, label: "0.5x · Very slow" },
  { value: 0.75, label: "0.75x · Slow" },
  { value: 1.0, label: "1.0x · Normal" },
  { value: 1.25, label: "1.25x · Fast" },
  { value: 1.5, label: "1.5x · Faster" },
  { value: 2.0, label: "2.0x · Very fast" },
];

const PREVIEW_TEXT: Record<string, string> = {
  hi: "नमस्ते! यह आपकी चुनी हुई आवाज़ का पूर्वावलोकन है।",
  mr: "नमस्कार! हा तुम्ही निवडलेल्या आवाजाचा नमुना आहे.",
  default: "Hello! This is a preview of the selected voice at the configured speed.",
};

export function VoiceSettingsForm({
  initial,
  showOverrideToggle,
  locked,
  onSave,
  onReset,
}: {
  initial: AdminVoiceSettings;
  /** Super Admin only: render the allow-tenant-override switch. */
  showOverrideToggle?: boolean;
  /** Tenant form when the platform disallows overrides: read-only + notice. */
  locked?: boolean;
  onSave: (values: Partial<AdminVoiceSettings>) => Promise<void>;
  /** Tenant form: revert to platform defaults. */
  onReset?: () => Promise<void>;
}) {
  const [form, setForm] = useState<AdminVoiceSettings>({ ...initial });
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const voices = useBrowserVoices();

  const set = <K extends keyof AdminVoiceSettings>(key: K, value: AdminVoiceSettings[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Languages the device actually has voices for.
  const languages = useMemo(() => {
    const langs = new Map<string, string>();
    for (const v of voices) {
      try {
        const label = new Intl.DisplayNames(["en"], { type: "language" }).of(v.lang.split("-")[0]);
        langs.set(v.lang, `${label || v.lang} (${v.lang})`);
      } catch {
        langs.set(v.lang, v.lang);
      }
    }
    return [...langs.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [voices]);

  const matchingVoices = useMemo(() => {
    const base = form.language
      ? voices.filter((v) => v.lang.toLowerCase().startsWith(form.language!.split("-")[0].toLowerCase()))
      : voices;
    return form.gender ? base.filter((v) => !voiceGender(v) || voiceGender(v) === form.gender) : base;
  }, [voices, form.language, form.gender]);

  const preview = () => {
    const lang = (form.language || "").split("-")[0];
    speakWithSettings(PREVIEW_TEXT[lang] || PREVIEW_TEXT.default, form, voices);
  };

  const save = async () => {
    setSaving(true);
    try {
      const body: Partial<AdminVoiceSettings> = {
        enabled: form.enabled,
        provider: form.provider || "browser",
        voice_name: form.voice_name || null,
        language: form.language || null,
        gender: form.gender || null,
        rate: clamp(form.rate, 0.5, 2),
        pitch: clamp(form.pitch, 0, 2),
        volume: clamp(form.volume, 0, 1),
        auto_play: form.auto_play,
      };
      if (showOverrideToggle) body.allow_tenant_override = form.allow_tenant_override;
      await onSave(body);
    } finally {
      setSaving(false);
    }
  };

  const disabled = locked || saving;

  return (
    <div className="space-y-4">
      {locked && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Tenant-level voice settings are currently disabled by the platform administrator. Your
          users receive the platform defaults below.
        </p>
      )}

      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <Toggle
          label="Voice playback"
          checked={form.enabled}
          onChange={(v) => set("enabled", v)}
          disabled={disabled}
        />
        <Toggle
          label="Auto-play responses"
          checked={form.auto_play}
          onChange={(v) => set("auto_play", v)}
          disabled={disabled}
        />
        {showOverrideToggle && (
          <Toggle
            label="Allow tenant overrides"
            checked={form.allow_tenant_override}
            onChange={(v) => set("allow_tenant_override", v)}
            disabled={saving}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="label">Provider</span>
          <select className="input" value={form.provider} disabled>
            <option value="browser">Browser / device voices</option>
          </select>
        </label>
        <label className="block">
          <span className="label">Language & locale</span>
          <select
            className="input"
            value={form.language || ""}
            disabled={disabled}
            onChange={(e) => setForm((f) => ({ ...f, language: e.target.value || null, voice_name: null }))}
          >
            <option value="">Auto (match the answer)</option>
            {languages.map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label">Voice gender (when available)</span>
          <select
            className="input"
            value={form.gender || ""}
            disabled={disabled}
            onChange={(e) => set("gender", (e.target.value || null) as VoiceGender | null)}
          >
            <option value="">Any</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="neutral">Neutral</option>
          </select>
        </label>
      </div>

      <label className="block">
        <span className="label">Voice ({matchingVoices.length} available on this device)</span>
        <select
          className="input"
          value={form.voice_name || ""}
          disabled={disabled}
          onChange={(e) => set("voice_name", e.target.value || null)}
        >
          <option value="">Automatic (best match for language)</option>
          {matchingVoices.map((v) => (
            <option key={`${v.name}|${v.lang}`} value={v.name}>
              {v.name} · {v.lang} · {v.localService ? "device" : "online"} · {voiceGender(v) || "—"}
            </option>
          ))}
        </select>
        <span className="mt-1 block text-[11px] text-slate-400">
          Voices differ per device. If a user's device lacks this voice, the closest voice for the
          answer's language is used automatically.
        </span>
      </label>

      <div>
        <span className="label">Speech speed</span>
        <div className="flex flex-wrap gap-1.5">
          {SPEED_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              disabled={disabled}
              onClick={() => set("rate", p.value)}
              className={cn(
                "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition",
                form.rate === p.value
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-slate-200 text-slate-600 hover:bg-slate-50",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <SliderRow
          label="Pitch"
          value={form.pitch}
          min={0}
          max={2}
          step={0.1}
          disabled={disabled}
          onChange={(v) => set("pitch", v)}
        />
        <SliderRow
          label="Volume"
          value={form.volume}
          min={0}
          max={1}
          step={0.05}
          disabled={disabled}
          onChange={(v) => set("volume", v)}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button type="button" className="btn-secondary" onClick={preview} disabled={saving}>
          <Icon.Speaker width={15} height={15} /> Preview voice
        </button>
        <button type="button" className="btn-primary" onClick={save} disabled={disabled}>
          {saving ? <Spinner className="text-white" /> : <Icon.Check width={15} height={15} />} Save settings
        </button>
        {onReset && initial.configured && !locked && (
          <button
            type="button"
            className="btn-ghost text-xs text-slate-500"
            disabled={resetting}
            onClick={async () => {
              setResetting(true);
              try {
                await onReset();
              } finally {
                setResetting(false);
              }
            }}
          >
            {resetting ? <Spinner /> : null} Reset to platform defaults
          </button>
        )}
      </div>
    </div>
  );
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number.isFinite(v) ? v : 1));

function Toggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex cursor-pointer items-center gap-2", disabled && "cursor-not-allowed opacity-60")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 rounded-full transition",
          checked ? "bg-brand-600" : "bg-slate-300",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
      <span className="text-sm font-medium text-slate-700">{label}</span>
    </label>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="label">
        {label}: <b>{value.toFixed(2)}</b>
      </span>
      <input
        type="range"
        className="w-full accent-brand-600"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </label>
  );
}
