"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { api, setAuthToken, setUnauthorizedHandler } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  token: string | null;
  /** 登录 / 注册请求进行中标记，用于按钮 loading 态。 */
  pending: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

function applySession(token: string, user: User) {
  setAuthToken(token);
  return { token, user };
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      pending: false,

      login: async (username, password) => {
        set({ pending: true });
        try {
          const res = await api.login({ username, password });
          set({ ...applySession(res.access_token, res.user), pending: false });
        } catch (error) {
          set({ pending: false });
          throw error;
        }
      },

      register: async (username, password) => {
        set({ pending: true });
        try {
          const res = await api.register({ username, password });
          set({ ...applySession(res.access_token, res.user), pending: false });
        } catch (error) {
          set({ pending: false });
          throw error;
        }
      },

      logout: () => {
        setAuthToken(null);
        set({ user: null, token: null, pending: false });
      },
    }),
    {
      name: "agent-assistant-auth",
      version: 1,
      // 只持久化登录态，pending 等瞬时状态不入库
      partialize: (state) => ({ user: state.user, token: state.token }),
      // 从 localStorage 恢复后立即把 token 注入 api 层，保证后续请求带上凭证
      onRehydrateStorage: () => (state) => {
        if (state?.token) setAuthToken(state.token);
      },
    },
  ),
);

// 令牌失效（401）时自动清除登录态，UI 会回到登录页
setUnauthorizedHandler(() => {
  setAuthToken(null);
  useAuthStore.setState({ user: null, token: null, pending: false });
});

export function isAuthenticated(state: AuthState): boolean {
  return Boolean(state.token && state.user);
}
