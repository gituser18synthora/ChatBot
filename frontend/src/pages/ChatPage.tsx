import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { chatApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { NewChatModal } from "@/components/chat/NewChatModal";
import { ChangePasswordModal } from "@/components/common/ChangePasswordModal";
import { MessageBubble, TypingBubble } from "@/components/chat/MessageBubble";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icons";
import { Spinner, EmptyState, Badge, LoadingBlock, ErrorState } from "@/components/ui/primitives";
import { useVoiceSettings } from "@/context/VoiceSettingsContext";
import { speakWithSettings, useVoiceInput } from "@/hooks/useSpeech";
import { cn, initials, relativeTime, roleLabel } from "@/lib/utils";
import type { ChatMessage, ChatSession } from "@/api/types";

export function ChatPage() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { settings: voiceSettings } = useVoiceSettings();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<ChatSession | null>(null);
  const [loadingActive, setLoadingActive] = useState(false);

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [newChat, setNewChat] = useState(false);
  const [toDelete, setToDelete] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [menu, setMenu] = useState(false);
  const [changingPw, setChangingPw] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load session list.
  const loadSessions = async () => {
    setLoadingSessions(true);
    setSessionsError(null);
    try {
      const res = await chatApi.listSessions({ per_page: 100 });
      setSessions(res.items);
    } catch (e: any) {
      setSessionsError(e.message);
    } finally {
      setLoadingSessions(false);
    }
  };
  useEffect(() => {
    loadSessions();
  }, []);

  // Load active session detail.
  useEffect(() => {
    if (!activeId) {
      setActive(null);
      return;
    }
    let ok = true;
    setLoadingActive(true);
    chatApi
      .getSession(activeId)
      .then((s) => ok && setActive(s))
      .catch((e) => ok && toast.error(e.message))
      .finally(() => ok && setLoadingActive(false));
    return () => {
      ok = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  // Autoscroll on new messages / typing.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [active?.messages?.length, sending]);

  const autoGrow = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  };

  // Voice input: dictation lands in the input field so the user can review or
  // edit before sending. While speaking, interim words preview live and are
  // replaced by the final transcript; the text typed before pressing the mic
  // is kept (voiceBaseRef).
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

  const filtered = useMemo(
    () => sessions.filter((s) => (s.title || "").toLowerCase().includes(search.toLowerCase())),
    [sessions, search],
  );

  const onCreated = (s: ChatSession) => {
    setNewChat(false);
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setActive({ ...s, messages: [] });
    setDrawer(false);
  };

  // Chat Users go straight into a new conversation — no dialog, their
  // Knowledge Bases apply automatically. Admins get the modal so they can
  // optionally pin the chat to specific KBs.
  const [creatingChat, setCreatingChat] = useState(false);
  const startNewChat = async () => {
    if (user?.role !== "chat_user") {
      setNewChat(true);
      return;
    }
    if (creatingChat) return;
    setCreatingChat(true);
    try {
      onCreated(await chatApi.createSession(null, []));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCreatingChat(false);
    }
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
      // The title is auto-generated from the first message — reflect it immediately.
      setActive((s) =>
        s
          ? { ...s, title: session_title ?? s.title, messages: [...(s.messages || []), assistant_message] }
          : s,
      );
      // Admin-configured auto-play: read the new answer aloud without a click.
      if (voiceSettings?.enabled && voiceSettings.auto_play && assistant_message.answer_mode !== "error") {
        speakWithSettings(assistant_message.message_text, voiceSettings, window.speechSynthesis?.getVoices() || []);
      }
      setSessions((list) =>
        list.map((x) => (x.id === activeId ? { ...x, title: session_title ?? x.title } : x)),
      );
      // Bump the session to the top.
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
      // Drop a trailing error/answer so the retry appends fresh.
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
        setActive(null);
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

  const Sidebar = (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Icon.Sparkle width={16} height={16} />
        </div>
        <span className="font-bold text-slate-900">Aurexion Chat</span>
      </div>
      <div className="px-3">
        <button className="btn-primary w-full" onClick={startNewChat} disabled={creatingChat}>
          {creatingChat ? <Spinner className="text-white" /> : <Icon.Plus width={16} height={16} />} New Chat
        </button>
      </div>
      <div className="px-3 py-3">
        <div className="relative">
          <Icon.Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width={15} height={15} />
          <input
            className="input py-1.5 pl-9 text-sm"
            placeholder="Search chats…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {loadingSessions ? (
          <LoadingBlock label="Loading chats…" />
        ) : sessionsError ? (
          <ErrorState message={sessionsError} onRetry={loadSessions} />
        ) : filtered.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-slate-400">No conversations yet.</p>
        ) : (
          filtered.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setActiveId(s.id);
                setDrawer(false);
              }}
              className={cn(
                "group mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition",
                activeId === s.id ? "bg-brand-50 text-brand-800" : "hover:bg-slate-100",
              )}
            >
              <Icon.Chat width={16} height={16} className="flex-none text-slate-400" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{s.title || "New Chat"}</span>
                <span className="block text-[11px] text-slate-400">{relativeTime(s.updated_at)}</span>
              </span>
              <span
                role="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setToDelete(s.id);
                }}
                className="flex-none rounded p-1 text-slate-300 opacity-0 hover:text-rose-500 group-hover:opacity-100"
              >
                <Icon.Trash width={15} height={15} />
              </span>
            </button>
          ))
        )}
      </div>
      {/* Profile */}
      <div className="relative border-t border-slate-100 p-3">
        <button
          onClick={() => setMenu((m) => !m)}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-slate-100"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
            {initials(user?.name || "U")}
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-sm font-semibold text-slate-800">{user?.name}</span>
            <span className="block text-[11px] text-slate-400">{roleLabel(user?.role)}</span>
          </span>
          <Icon.ChevronDown width={16} height={16} className="text-slate-400" />
        </button>
        {menu && (
          <div className="absolute inset-x-3 bottom-16 z-10 animate-fade-in-up rounded-xl border border-slate-200 bg-white p-1.5 shadow-pop">
            {user?.role !== "chat_user" && (
              <button
                onClick={() => navigate("/admin")}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                <Icon.Dashboard width={16} height={16} /> Admin Console
              </button>
            )}
            <button
              onClick={() => {
                setMenu(false);
                setChangingPw(true);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              <Icon.Settings width={16} height={16} /> Change password
            </button>
            <button
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50"
            >
              <Icon.Logout width={16} height={16} /> Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="hidden w-72 flex-none border-r border-slate-200 md:block">{Sidebar}</aside>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setDrawer(false)} />
          <aside className="absolute left-0 top-0 h-full w-80 animate-fade-in-up shadow-pop">{Sidebar}</aside>
        </div>
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 flex-none items-center gap-3 border-b border-slate-200 bg-white px-3 sm:px-5">
          <button className="btn-ghost rounded-lg p-2 md:hidden" onClick={() => setDrawer(true)} aria-label="Open chats">
            <Icon.Menu />
          </button>
          {active ? (
            <>
              <div className="min-w-0 flex-1">
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
                    <span className="truncate">{active.title || "New Chat"}</span>
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
                className="btn-ghost rounded-lg p-2 text-rose-500 hover:bg-rose-50"
                onClick={() => setToDelete(active.id)}
                aria-label="Delete chat"
              >
                <Icon.Trash width={18} height={18} />
              </button>
            </>
          ) : (
            <span className="text-sm font-semibold text-slate-500">Select or start a chat</span>
          )}
        </header>

        {/* Messages */}
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
            ) : (active?.messages?.length || 0) === 0 ? (
              <div className="flex h-full items-center justify-center py-20">
                <EmptyState
                  icon={<Icon.Sparkle />}
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
                {active?.messages?.map((m, i) => (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    onRetry={i === (active.messages!.length - 1) && m.role === "assistant" ? retryLast : undefined}
                  />
                ))}
                {sending && <TypingBubble />}
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        {activeId && (
          <div className="flex-none border-t border-slate-200 bg-white px-3 py-3 sm:px-6">
            <div className="mx-auto max-w-3xl">
              <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100">
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
    </div>
  );
}
