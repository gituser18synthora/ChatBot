import { useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { NewChatModal } from "@/components/chat/NewChatModal";
import { ChangePasswordModal } from "@/components/common/ChangePasswordModal";
import { MessageBubble, TypingBubble } from "@/components/chat/MessageBubble";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icons";
import { Spinner, EmptyState, Badge, LoadingBlock } from "@/components/ui/primitives";
import { useVoiceSettings } from "@/context/VoiceSettingsContext";
import { speakWithSettings, useVoiceInput } from "@/hooks/useSpeech";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/api/types";
import { chatApi } from "@/api/services";
import { useChat } from "@/context/ChatContext";
import { AppLayout } from "@/components/layout/AdminLayout";
import { ChatProvider } from "@/context/ChatContext";
import icon from "../assets/favicon.svg"
// ─── Inner chat view (uses ChatContext) ──────────────────────────────────────

function ChatView() {
  const { user } = useAuth();
  const toast = useToast();
  const { settings: voiceSettings } = useVoiceSettings();

  const {
    active,
    setActive,
    activeId,
    setActiveId,
    setSessions,
    loadSessions,
    loadingActive,
    newChat,
    setNewChat,
    onCreated,
    creatingChat,
    startNewChat,
  } = useChat();

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [toDelete, setToDelete] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [changingPw, setChangingPw] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoGrow = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  };

  const voiceBaseRef = useRef("");
  const voice = useVoiceInput((text, isFinal) => {
    const base = voiceBaseRef.current;
    const joined = (base ? base.replace(/\s+$/, "") + " " : "") + text;
    setInput(joined);
    if (isFinal) voiceBaseRef.current = joined;
    setTimeout(autoGrow, 0);
  });

  const toggleVoice = () => {
    if (!voice.listening) voiceBaseRef.current = input;
    voice.toggle();
    textareaRef.current?.focus();
  };

  const send = async (text: string) => {
    if (!text.trim() || !activeId || sending) return;
    const userMsg: ChatMessage = {
      id: `tmp-${Date.now()}`,
      chat_session_id: activeId,
      role: "user",
      message_text: text.trim(),
      answer_mode: null,
      model_name: null,
      total_tokens: 0,
      estimated_cost_usd: 0,
      latency_ms: null,
      created_at: new Date().toISOString(),
    };
    setActive((s) => (s ? { ...s, messages: [...(s.messages || []), userMsg] } : s));
    setInput("");
    voiceBaseRef.current = "";
    if (voice.listening) voice.stop();
    setTimeout(autoGrow, 0);
    setSending(true);
    try {
      const { assistant_message, session_title } = await chatApi.send(activeId, text.trim());
      setActive((s) =>
        s
          ? { ...s, title: session_title ?? s.title, messages: [...(s.messages || []), assistant_message] }
          : s,
      );
      if (voiceSettings?.enabled && voiceSettings.auto_play && assistant_message.answer_mode !== "error") {
        speakWithSettings(assistant_message.message_text, voiceSettings, window.speechSynthesis?.getVoices() || []);
      }
      setSessions((list) =>
        list.map((x) => (x.id === activeId ? { ...x, title: session_title ?? x.title } : x)),
      );
      loadSessions();
    } catch (e: any) {
      const errMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        chat_session_id: activeId,
        role: "assistant",
        message_text: e.message || "Something went wrong. Please try again.",
        answer_mode: "error",
        model_name: null,
        total_tokens: 0,
        estimated_cost_usd: 0,
        latency_ms: null,
        created_at: new Date().toISOString(),
      };
      setActive((s) => (s ? { ...s, messages: [...(s.messages || []), errMsg] } : s));
    } finally {
      setSending(false);
    }
  };

  const retryLast = () => {
    const msgs = active?.messages || [];
    const lastUser = [...msgs].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setActive((s) => {
        if (!s) return s;
        const m = [...(s.messages || [])];
        if (m.length && m[m.length - 1].role === "assistant") m.pop();
        return { ...s, messages: m };
      });
      send(lastUser.message_text);
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    try {
      await chatApi.remove(toDelete);
      setSessions((s) => s.filter((x) => x.id !== toDelete));
      if (activeId === toDelete) {
        setActiveId(null);
      }
      toast.success("Conversation deleted.");
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setToDelete(null);
    }
  };

  const submitRename = async () => {
    if (!activeId || !renameValue.trim()) {
      setRenaming(false);
      return;
    }
    try {
      const updated = await chatApi.rename(activeId, renameValue.trim());
      setActive((s) => (s ? { ...s, title: updated.title } : s));
      setSessions((list) => list.map((x) => (x.id === activeId ? { ...x, title: updated.title } : x)));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setRenaming(false);
    }
  };

  // Topbar content passed up to AppLayout
  const topbarContent = active ? (
    <div className="flex gap-2">
      <div className="min-w-0 flex items-center justify-content">
        {renaming ? (
          <input
            autoFocus
            className="input py-1 text-sm"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={submitRename}
            onKeyDown={(e) => e.key === "Enter" && submitRename()}
          />
        ) : (
          <button
            className="flex items-center gap-2 truncate text-sm font-semibold text-slate-800"
            onClick={() => {
              setRenameValue(active.title || "");
              setRenaming(true);
            }}
            title="Rename"
          >
            <span className="truncate text-white">{active.title || "New Chat"}</span>
            <Icon.Edit width={14} height={14} className="flex-none text-slate-300" />
          </button>
        )}
        {active.kb_names && active.kb_names.filter(Boolean).length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1">
            {active.kb_names.filter(Boolean).map((n, i) => (
              <Badge key={i} tone="blue">
                <Icon.Book width={11} height={11} /> {n}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <button
        className="btn-ghost rounded-lg p-2 text-rose-500"
        onClick={() => setToDelete(active.id)}
        aria-label="Delete chat"
      >
        <Icon.Trash width={18} height={18} />
      </button>
    </div>
  ) : (
    <span className="text-sm font-semibold text-white">Select or start a New chat</span>
  );

  return (
    <AppLayout mode="chat" topbarContent={topbarContent} onChangePw={() => setChangingPw(true)}>
      <div className="flex h-full flex-col">
      {/* Messages area */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-6 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {!activeId ? (
            <div className="flex h-full items-center justify-center py-20">
              <EmptyState
                icon={<Icon.Chat />}
                title="Start a conversation"
                description={
                  user?.role === "chat_user"
                    ? "Start a new chat and ask a question. Your Knowledge Bases are used automatically."
                    : "Create a new chat and ask a question. Select knowledge bases to get answers grounded in your documents."
                }
                action={
                  <button className="btn-primary" onClick={startNewChat} disabled={creatingChat}>
                    {creatingChat ? <Spinner className="text-white" /> : <Icon.Plus width={16} height={16} />} New Chat
                  </button>
                }
              />
            </div>
          ) : loadingActive ? (
            <LoadingBlock label="Loading conversation…" />
          ) : !active || (active.messages?.length ?? 0) === 0 ? (
            <div className="flex h-full items-center justify-center py-20">
              <EmptyState
                icon={<img src={icon} width={16} height={16} alt="Logo" />}
                title="Ask your first question"
                description={
                  user?.role === "chat_user"
                    ? "Your Knowledge Bases are used automatically."
                    : active?.kb_ids?.length
                      ? "This chat is grounded in your selected knowledge bases."
                      : "This is a general AI chat. Ask anything."
                }
              />
            </div>
          ) : (
            <div className="space-y-5">
              {active.messages?.map((m, i) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onRetry={
                    i === ((active.messages?.length ?? 0) - 1) && m.role === "assistant"
                      ? retryLast
                      : undefined
                  }
                />
              ))}
              {sending && <TypingBubble />}
            </div>
          )}
        </div>
      </div>
      {activeId && (
        <div className="flex-none border-t border-slate-200 bg-white px-3 py-3 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-center gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100">
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                disabled={sending}
                onChange={(e) => {
                  setInput(e.target.value);
                  autoGrow();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                placeholder={
                  voice.listening ? "Listening… speak now" : "Message… (Enter to send, Shift+Enter for a new line)"
                }
                className="max-h-44 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-slate-400"
              />
              {voice.supported && (
                <button
                  className={cn(
                    "flex-none rounded-xl p-2.5 transition",
                    voice.listening
                      ? "animate-pulse bg-rose-50 text-rose-600"
                      : "text-slate-400 hover:bg-slate-100 hover:text-slate-600",
                  )}
                  disabled={sending}
                  onClick={toggleVoice}
                  aria-label={voice.listening ? "Stop voice input" : "Speak your message"}
                  title={voice.listening ? "Stop voice input" : "Speak your message"}
                >
                  <Icon.Mic width={18} height={18} />
                </button>
              )}
              <button
                className="btn-primary flex-none rounded-xl px-3 py-2.5"
                disabled={!input.trim() || sending}
                onClick={() => send(input)}
                aria-label="Send"
              >
                {sending ? <Spinner className="text-white" /> : <Icon.Send width={18} height={18} />}
              </button>
            </div>
            <div className="mt-1 flex justify-between px-1 text-[11px] text-slate-400">
              <span>Answers grounded in documents show their sources.</span>
              <span>{input.length}/8000</span>
            </div>
          </div>
        </div>
      )}

      </div>
      {newChat && <NewChatModal onClose={() => setNewChat(false)} onCreated={onCreated} />}
      {changingPw && <ChangePasswordModal onClose={() => setChangingPw(false)} />}
      <ConfirmDialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={remove}
        danger
        title="Delete conversation"
        confirmLabel="Delete"
        message="This permanently deletes the conversation and its messages."
      />
    </AppLayout>
  );
}

export function ChatPage() {
  return (
    <ChatProvider>
      <ChatView />
    </ChatProvider>
  );
}
