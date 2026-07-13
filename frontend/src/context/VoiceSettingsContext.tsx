/**
 * Effective TTS voice settings for the signed-in user (tenant > platform >
 * builtin, merged by the backend). Loaded once per login and refreshable —
 * admin saves call refresh() so new playback picks the change up without a
 * page reload (spec §7).
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { voiceApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import type { EffectiveVoiceSettings } from "@/api/types";

interface VoiceCtx {
  settings: EffectiveVoiceSettings | null;
  refresh: () => Promise<void>;
}

const Ctx = createContext<VoiceCtx>({ settings: null, refresh: async () => {} });

export function VoiceSettingsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [settings, setSettings] = useState<EffectiveVoiceSettings | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSettings(await voiceApi.getEffective());
    } catch {
      setSettings(null); // playback falls back to browser defaults
    }
  }, []);

  useEffect(() => {
    if (user) refresh();
    else setSettings(null);
  }, [user, refresh]);

  return <Ctx.Provider value={{ settings, refresh }}>{children}</Ctx.Provider>;
}

export function useVoiceSettings(): VoiceCtx {
  return useContext(Ctx);
}
