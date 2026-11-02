"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export const queryKeys = {
  health: ["health"] as const,
  files: ["files"] as const,
  history: (sessionId: string) => ["history", sessionId] as const,
};

/** 服务健康状态：挂载后开启，每 30 秒轮询一次。 */
export function useHealthQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    enabled,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    staleTime: 10_000,
  });
}

/** 知识库文件列表，上传 / 删除后由调用方 invalidate。 */
export function useFilesQuery(enabled = true) {
  return useQuery({
    queryKey: queryKeys.files,
    queryFn: ({ signal }) => api.files(signal),
    enabled,
    refetchOnWindowFocus: false,
    retry: 1,
    staleTime: 10_000,
  });
}
