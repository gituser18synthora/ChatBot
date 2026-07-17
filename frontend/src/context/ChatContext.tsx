import React, { createContext, useContext, useState, useEffect } from "react";
import { chatApi } from "@/api/services";
import { useToast } from "@/context/ToastContext";
import { useAuth } from "@/context/AuthContext";
import type { ChatSession } from "@/api/types";

interface ChatContextType {
  sessions: ChatSession[];
  setSessions: React.Dispatch<React.SetStateAction<ChatSession[]>>;
  loadingSessions: boolean;
  sessionsError: string | null;
  activeId: string | null;
  setActiveId: (id: string | null) => void;
  active: ChatSession | null;
  setActive: React.Dispatch<React.SetStateAction<ChatSession | null>>;
  search: string;
  setSearch: (s: string) => void;
  creatingChat: boolean;
  startNewChat: () => Promise<void>;
  loadSessions: () => Promise<void>;
  onCreated: (s: ChatSession) => void;
  newChat: boolean;
  setNewChat: (open: boolean) => void;
  loadingActive: boolean;
  setLoadingActive: (loading: boolean) => void;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const toast = useToast();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<ChatSession | null>(null);
  const [search, setSearch] = useState("");
  const [creatingChat, setCreatingChat] = useState(false);
  const [newChat, setNewChat] = useState(false);
  const [loadingActive, setLoadingActive] = useState(false);

  const loadSessions = async () => {
    if (!user) return;
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
    if (user) {
      loadSessions();
    } else {
      setSessions([]);
      setActiveId(null);
      setActive(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

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

  const onCreated = (s: ChatSession) => {
    setNewChat(false);
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setActive({ ...s, messages: [] });
  };

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

  return (
    <ChatContext.Provider
      value={{
        sessions,
        setSessions,
        loadingSessions,
        sessionsError,
        activeId,
        setActiveId,
        active,
        setActive,
        search,
        setSearch,
        creatingChat,
        startNewChat,
        loadSessions,
        onCreated,
        newChat,
        setNewChat,
        loadingActive,
        setLoadingActive,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) throw new Error("useChat must be used within ChatProvider");
  return context;
}
