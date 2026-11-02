"use client";

import { useSyncExternalStore } from "react";

// 不订阅任何外部事件，只在 hydration 完成后从 false 切换为 true。
const subscribe = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

/**
 * SSR / hydration 首帧返回 false，挂载后返回 true。
 * 避免 hydration mismatch，也让 TanStack Query 只在客户端启动。
 */
export function useMounted(): boolean {
  return useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
}
