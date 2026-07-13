/**
 * Browser speech features for the chat UI, built on the Web Speech API —
 * no backend calls, no audio uploads, works offline-ish on device voices.
 *
 * - useSpeaker(): text-to-speech playback of an assistant answer, driven by
 *   the admin-configured voice settings (rate/pitch/volume/voice preference).
 * - useVoiceInput(): microphone dictation into the message input.
 * - useBrowserVoices(): the device's available voices (admin pickers).
 * - resolveVoice(): preference -> best available device voice, with fallback
 *   by the ANSWER's language when the configured voice can't speak it.
 *
 * Support: speechSynthesis is universal; SpeechRecognition exists in Chrome,
 * Edge, Android WebView and iOS/macOS Safari (webkit prefix) but NOT Firefox —
 * both hooks expose `supported` so the UI simply hides the control there.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { VoiceSettings } from "@/api/types";

// ── Text-to-speech ────────────────────────────────────────────

/** Markdown → plain speakable text: strip syntax the TTS engine would read
 * aloud ("asterisk asterisk…") and drop code blocks/tables entirely. */
export function speakableText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ") // fenced code blocks
    .replace(/^\s*\|.*\|\s*$/gm, " ") // table rows
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ") // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → their text
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/(\*\*|__|\*|_|~~)/g, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Best-effort gender from a voice's name — many providers don't expose one,
 * so this may return null and the UI shows "—" (spec §4). */
export function voiceGender(voice: SpeechSynthesisVoice): "male" | "female" | null {
  const n = voice.name.toLowerCase();
  if (/female|woman|feminine|\bheera\b|\bkalpana\b|\bswara\b|\bveena\b|\bzira\b|\bsusan\b|\bsamantha\b/.test(n)) return "female";
  if (/\bmale\b|\bman\b|masculine|\bravi\b|\bhemant\b|\bmadhur\b|\bdavid\b|\bmark\b|\bdaniel\b/.test(n)) return "male";
  return null;
}

/** Language of the text to be spoken: Devanagari answers resolve to Hindi or
 * Marathi (function-word vote); Latin text has no intrinsic preference. */
export function textLanguage(text: string): "hi" | "mr" | null {
  const devanagari = (text.match(/[ऀ-ॿ]/g) || []).length;
  const letters = (text.match(/[A-Za-zऀ-ॿ]/g) || []).length || 1;
  if (devanagari / letters <= 0.3) return null;
  return /(आहे|आहेत|नाही|तुम्ही|मध्ये|आणि)/.test(text) ? "mr" : "hi";
}

export interface ResolvedVoice {
  voice: SpeechSynthesisVoice | null;
  /** false when the configured voice/language was unavailable and a
   * compatible substitute (or the browser default) is used instead. */
  exact: boolean;
}

/** Preference -> best available device voice (spec §6 fallback chain):
 * 1. the configured voice by name, unless the answer is in a language that
 *    voice cannot speak; 2. a voice for the answer's language (gender
 *    preference respected when derivable); 3. a voice for the configured
 *    language; 4. the browser default. */
export function resolveVoice(
  voices: SpeechSynthesisVoice[],
  prefs: Pick<VoiceSettings, "voice_name" | "language" | "gender"> | null,
  text: string,
): ResolvedVoice {
  const answerLang = textLanguage(text);
  const wantLangs = answerLang ? [answerLang] : prefs?.language ? [prefs.language] : [];

  const speaks = (v: SpeechSynthesisVoice, lang: string) =>
    v.lang.toLowerCase().startsWith(lang.split("-")[0].toLowerCase());

  const named = prefs?.voice_name ? voices.find((v) => v.name === prefs.voice_name) : null;
  if (named && (wantLangs.length === 0 || wantLangs.some((l) => speaks(named, l)))) {
    return { voice: named, exact: true };
  }

  const candidates = ([] as string[])
    .concat(answerLang ? [answerLang === "mr" ? "mr" : "hi", "hi"] : [])
    .concat(prefs?.language && !answerLang ? [prefs.language] : []);
  for (const lang of candidates) {
    const pool = voices.filter((v) => speaks(v, lang));
    if (!pool.length) continue;
    const byGender = prefs?.gender ? pool.find((v) => voiceGender(v) === prefs.gender) : null;
    // Matching the CONFIGURED language (auto voice) is the intended outcome,
    // not a fallback; only a language switch or missing named voice is.
    const configuredMatch =
      !prefs?.voice_name &&
      !!prefs?.language &&
      lang.split("-")[0].toLowerCase() === prefs.language.split("-")[0].toLowerCase();
    return { voice: byGender || pool[0], exact: configuredMatch };
  }
  // Nothing matched: named voice missing or no language voice on this device.
  return { voice: named || null, exact: !prefs?.voice_name && !prefs?.language };
}

/** The device's speech voices; refreshes when the browser loads them async. */
export function useBrowserVoices(): SpeechSynthesisVoice[] {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() =>
    supported ? window.speechSynthesis.getVoices() : [],
  );
  useEffect(() => {
    if (!supported) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener?.("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", load);
  }, [supported]);
  return voices;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Fire-and-forget utterance with settings applied. Shared by chat playback
 * and the admin Preview button. Returns the utterance or null. */
export function speakWithSettings(
  text: string,
  settings: Partial<VoiceSettings> | null,
  voices: SpeechSynthesisVoice[],
): { utterance: SpeechSynthesisUtterance; exact: boolean } | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const plain = speakableText(text);
  if (!plain) return null;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(plain);
  const { voice, exact } = resolveVoice(
    voices,
    settings
      ? { voice_name: settings.voice_name ?? null, language: settings.language ?? null, gender: settings.gender ?? null }
      : null,
    plain,
  );
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  } else if (settings?.language) {
    utterance.lang = settings.language;
  }
  utterance.rate = clamp(settings?.rate ?? 1, 0.5, 2);
  utterance.pitch = clamp(settings?.pitch ?? 1, 0, 2);
  utterance.volume = clamp(settings?.volume ?? 1, 0, 1);
  window.speechSynthesis.speak(utterance);
  return { utterance, exact };
}

export function useSpeaker(
  settings?: Partial<VoiceSettings> | null,
  onFallback?: (message: string) => void,
) {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speaking, setSpeaking] = useState(false);
  const activeRef = useRef<SpeechSynthesisUtterance | null>(null);
  const voices = useBrowserVoices();
  const onFallbackRef = useRef(onFallback);
  onFallbackRef.current = onFallback;

  // Stop playback when the message unmounts (chat switched / deleted).
  useEffect(
    () => () => {
      if (activeRef.current) window.speechSynthesis.cancel();
    },
    [],
  );

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (markdown: string) => {
      if (!supported) return;
      // One answer plays at a time: cancelling fires onend on any utterance
      // another bubble started, so its button resets itself.
      const result = speakWithSettings(markdown, settings ?? null, voices);
      if (!result) return;
      if (!result.exact && (settings?.voice_name || settings?.language)) {
        onFallbackRef.current?.(
          "The configured voice isn't available on this device — using the closest matching voice.",
        );
      }
      result.utterance.onend = () => setSpeaking(false);
      result.utterance.onerror = () => setSpeaking(false);
      activeRef.current = result.utterance;
      setSpeaking(true);
    },
    [supported, settings, voices],
  );

  return { supported, speaking, speak, stop };
}

// ── Voice input (dictation) ───────────────────────────────────

type RecognitionCtor = new () => any;

function getRecognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function useVoiceInput(onTranscript: (text: string, isFinal: boolean) => void) {
  const supported = getRecognitionCtor() !== null;
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  useEffect(
    () => () => {
      recognitionRef.current?.abort?.();
    },
    [],
  );

  const stop = useCallback(() => {
    recognitionRef.current?.stop?.();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor || recognitionRef.current) return;
    const recognition = new Ctor();
    // Browser/device locale decides the dictation language (an hi-IN phone
    // dictates Hindi). interimResults gives live text while speaking.
    recognition.lang = navigator.language || "en-IN";
    recognition.interimResults = true;
    recognition.continuous = false; // stops itself after a pause — natural on mobile

    recognition.onresult = (event: any) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interimText += r[0].transcript;
      }
      if (finalText) onTranscriptRef.current(finalText, true);
      else if (interimText) onTranscriptRef.current(interimText, false);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };
    recognition.onerror = () => {
      recognitionRef.current = null;
      setListening(false);
    };

    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setListening(false);
    }
  }, []);

  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);

  return { supported, listening, start, stop, toggle };
}
