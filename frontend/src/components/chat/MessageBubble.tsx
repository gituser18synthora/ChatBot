import { Suspense, lazy, useRef, useState } from "react";
import { SourceCards } from "./SourceCard";
import { Icon } from "@/components/ui/Icons";
import { Badge } from "@/components/ui/primitives";
import { useToast } from "@/context/ToastContext";
import { useVoiceSettings } from "@/context/VoiceSettingsContext";
import { useSpeaker } from "@/hooks/useSpeech";
import { cn } from "@/lib/utils";
import type { AnswerMode, ChatMessage } from "@/api/types";
import logo from '../../assets/icon-logo.png'

// The markdown stack (react-markdown + KaTeX + highlight.js) is heavy, so it
// loads on demand: admin pages never fetch it, and the chat fetches it once.
const Markdown = lazy(() => import("./Markdown").then((m) => ({ default: m.Markdown })));

function ModeBadge({ mode }: { mode: AnswerMode | null }) {
  switch (mode) {
    case "document_rag":
      return (
        <Badge tone="blue">
          <Icon.Book width={12} height={12} /> Knowledge Base Answer
        </Badge>
      );
    case "mixed":
      return <Badge tone="purple">Mixed Answer</Badge>;
    case "no_document_evidence":
      return <Badge tone="amber">No Supporting Evidence</Badge>;
    case "error":
      return <Badge tone="red">Error</Badge>;
    case "normal":
      return (
        <Badge tone="gray">
          <Icon.Sparkle width={12} height={12} /> General AI
        </Badge>
      );
    default:
      return null;
  }
}

export function MessageBubble({
  message,
  onRetry,
  readOnly,
}: {
  message: ChatMessage;
  onRetry?: () => void;
  readOnly?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const toast = useToast();
  const { settings: voiceSettings } = useVoiceSettings();
  // The fallback notice ("configured voice unavailable") shows once per
  // message, not on every replay.
  const warnedRef = useRef(false);
  const speaker = useSpeaker(voiceSettings, (msg) => {
    if (!warnedRef.current) {
      warnedRef.current = true;
      toast.info(msg);
    }
  });
  const isUser = message.role === "user";

  const copy = async () => {
    await navigator.clipboard.writeText(message.message_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (isUser) {
    return (
      <div className="flex animate-fade-in-up justify-end gap-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
          <p className="whitespace-pre-wrap break-words">{message.message_text}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-in-up gap-3">
      <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand-700 text-white">
        <img src={logo} width={16} height={16} alt="Logo" />
      </span>
      <div className="min-w-0 max-w-[85%]">
        <div
          className={cn(
            "rounded-2xl rounded-tl-sm border px-4 py-3 text-sm shadow-sm",
            message.answer_mode === "no_document_evidence"
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : message.answer_mode === "error"
                ? "border-rose-200 bg-rose-50 text-rose-800"
                : "border-slate-200 bg-white text-slate-800",
          )}
        >
          <div className="mb-1.5">
            <ModeBadge mode={message.answer_mode} />
          </div>
          {message.answer_mode === "error" || message.answer_mode === "no_document_evidence" ? (
            // Service/state notices are plain fixed strings — keep them as text.
            <p className="whitespace-pre-wrap break-words leading-relaxed">{message.message_text}</p>
          ) : (
            <Suspense
              fallback={<p className="whitespace-pre-wrap break-words leading-relaxed">{message.message_text}</p>}
            >
              <Markdown>{message.message_text}</Markdown>
            </Suspense>
          )}
          <SourceCards sources={message.sources || []} />
        </div>
        <div className="mt-1.5 flex items-center gap-3 px-1 text-xs text-slate-400">
          <button onClick={copy} className="inline-flex items-center gap-1 hover:text-slate-600">
            {copied ? <Icon.Check width={13} height={13} /> : <Icon.Copy width={13} height={13} />}
            {copied ? "Copied" : "Copy"}
          </button>
          {speaker.supported && voiceSettings?.enabled !== false && message.answer_mode !== "error" && (
            <button
              onClick={() => (speaker.speaking ? speaker.stop() : speaker.speak(message.message_text))}
              className={cn(
                "inline-flex items-center gap-1 hover:text-slate-600",
                speaker.speaking && "text-brand-600",
              )}
              aria-label={speaker.speaking ? "Stop audio" : "Listen to this answer"}
            >
              {speaker.speaking ? <Icon.Stop width={13} height={13} /> : <Icon.Speaker width={13} height={13} />}
              {speaker.speaking ? "Stop" : "Listen"}
            </button>
          )}
          {!readOnly && onRetry && (
            <button onClick={onRetry} className="inline-flex items-center gap-1 hover:text-slate-600">
              <Icon.Retry width={13} height={13} /> Retry
            </button>
          )}
          {message.model_name && <span className="hidden sm:inline">{message.model_name}</span>}
          {message.latency_ms != null && <span className="hidden sm:inline">· {message.latency_ms}ms</span>}
        </div>
      </div>
    </div>
  );
}

export function TypingBubble() {
  return (
    <div className="flex animate-fade-in-up gap-3">
      <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand-700 text-white">
        <img src={logo} width={16} height={16} alt="Logo" />
      </span>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
        <span className="typing-dot h-2 w-2 rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
        <span className="typing-dot h-2 w-2 rounded-full bg-slate-400" style={{ animationDelay: "150ms" }} />
        <span className="typing-dot h-2 w-2 rounded-full bg-slate-400" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}
