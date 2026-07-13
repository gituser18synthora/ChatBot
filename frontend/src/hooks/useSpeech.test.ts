import { describe, expect, it } from "vitest";
import { resolveVoice, speakableText, textLanguage, voiceGender } from "./useSpeech";

const v = (name: string, lang: string) =>
  ({ name, lang, localService: true, default: false, voiceURI: name }) as SpeechSynthesisVoice;

const VOICES = [
  v("Daniel English UK", "en-GB"),
  v("Microsoft Heera - English (India)", "en-IN"),
  v("Google हिन्दी", "hi-IN"),
  v("Marathi India", "mr-IN"),
];

describe("textLanguage", () => {
  it("detects Hindi, Marathi and Latin text", () => {
    expect(textLanguage("प्रीमियम 5000 रुपये है।")).toBe("hi");
    expect(textLanguage("प्रीमियम 5000 रुपये आहे आणि देय आहे.")).toBe("mr");
    expect(textLanguage("The premium is Rs. 5000.")).toBeNull();
  });
});

describe("voiceGender", () => {
  it("derives gender from the name when possible, else null", () => {
    expect(voiceGender(VOICES[1])).toBe("female"); // Heera
    expect(voiceGender(VOICES[0])).toBe("male"); // Daniel
    expect(voiceGender(VOICES[3])).toBeNull();
  });
});

describe("resolveVoice", () => {
  it("uses the configured voice by exact name for compatible text", () => {
    const r = resolveVoice(VOICES, { voice_name: "Daniel English UK", language: null, gender: null }, "Hello there");
    expect(r.voice?.name).toBe("Daniel English UK");
    expect(r.exact).toBe(true);
  });

  it("switches to a Hindi voice when the answer is Devanagari (spec §6)", () => {
    const r = resolveVoice(VOICES, { voice_name: "Daniel English UK", language: "en-GB", gender: null }, "प्रीमियम कितना है?");
    expect(r.voice?.lang).toBe("hi-IN");
    expect(r.exact).toBe(false); // fallback → UI may notify once
  });

  it("prefers a Marathi voice for Marathi answers, falling back to Hindi", () => {
    const marathi = "प्रीमियम ५००० रुपये आहे आणि तो देय आहे.";
    expect(resolveVoice(VOICES, null, marathi).voice?.lang).toBe("mr-IN");
    const noMarathi = VOICES.filter((x) => x.lang !== "mr-IN");
    expect(resolveVoice(noMarathi, null, marathi).voice?.lang).toBe("hi-IN");
  });

  it("auto voice for the configured language is NOT a fallback", () => {
    const r = resolveVoice(VOICES, { voice_name: null, language: "hi-IN", gender: null }, "Hello");
    expect(r.voice?.lang).toBe("hi-IN");
    expect(r.exact).toBe(true);
  });

  it("respects the gender preference when derivable", () => {
    const r = resolveVoice(
      VOICES,
      { voice_name: null, language: "en-IN", gender: "female" },
      "Hello",
    );
    expect(r.voice?.name).toContain("Heera");
  });

  it("no preferences and no special language → browser default (null voice, no fallback)", () => {
    const r = resolveVoice(VOICES, null, "Hello");
    expect(r.voice).toBeNull();
    expect(r.exact).toBe(true);
  });
});

describe("speakableText", () => {
  it("strips markdown syntax so TTS never reads symbols aloud", () => {
    const md = "## Premium\n\nThe **premium** is `Rs. 5000`, see [the policy](https://x.y).\n\n- yearly\n- *auto-debit*";
    expect(speakableText(md)).toBe("Premium The premium is Rs. 5000, see the policy. yearly auto-debit");
  });

  it("drops code blocks and table rows entirely", () => {
    const md = "Before\n```py\nprint(1)\n```\n| a | b |\n|---|---|\n| 1 | 2 |\nAfter";
    expect(speakableText(md)).toBe("Before After");
  });

  it("keeps non-Latin text intact", () => {
    expect(speakableText("**प्रीमियम** 5000 रुपये है।")).toBe("प्रीमियम 5000 रुपये है।");
  });

  it("returns empty string for empty input", () => {
    expect(speakableText("")).toBe("");
  });
});
