"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { DEFAULT_SESSION_ID, MAX_SESSION_LENGTH } from "@/lib/constants";

interface SessionState {
  sessionId: string;
  setSessionId: (sessionId: string) => void;
}

export function normalizeSessionId(value: string): string {
  const trimmed = value.trim().slice(0, MAX_SESSION_LENGTH);
  return trimmed || DEFAULT_SESSION_ID;
}

/** 当前会话 ID 持久化到 localStorage，刷新页面后继续原会话。 */
export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: DEFAULT_SESSION_ID,
      setSessionId: (sessionId) => set({ sessionId: normalizeSessionId(sessionId) }),
    }),
    {
      name: "agent-assistant-session",
      version: 1,
    },
  ),
);

/** 生成形如 chat-20261101-1530-a1b2c3d4 的新会话 ID。 */
export function createSessionId(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `chat-${stamp}-${random}`;
}
