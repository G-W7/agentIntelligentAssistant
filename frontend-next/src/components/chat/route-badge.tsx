"use client";

import {
  BookOpen,
  Brain,
  CloudSun,
  Code,
  Database,
  FileText,
  Globe,
  MessageSquare,
  Search,
  Sparkles,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useSkillsQuery } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import type { Route } from "@/lib/types";

type RouteMeta = { label: string; icon: string; color: string };

// 技能列表未加载完成、或历史消息里出现旧路由值时的兜底展示。
const FALLBACK_META: Record<string, RouteMeta> = {
  rag: { label: "知识库", icon: "book-open", color: "emerald" },
  search: { label: "联网搜索", icon: "search", color: "sky" },
  chat: { label: "通用对话", icon: "message-square", color: "violet" },
  mcp: { label: "工具调用", icon: "wrench", color: "amber" },
};

// 精选图标映射（kebab-case → 组件）。用显式具名导入而非 `import * as Icons`，
// 避免把整套 lucide 图标打进客户端 bundle；自定义技能可从此集合中选用图标名。
const ICONS: Record<string, LucideIcon> = {
  "book-open": BookOpen,
  brain: Brain,
  "cloud-sun": CloudSun,
  code: Code,
  database: Database,
  "file-text": FileText,
  globe: Globe,
  "message-square": MessageSquare,
  search: Search,
  sparkles: Sparkles,
  wrench: Wrench,
};

// 配色 key → 完整 Tailwind 类名（必须写全，动态拼接会被 JIT 清除）。
const COLOR_CLASSES: Record<string, string> = {
  emerald:
    "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  sky: "border-sky-500/20 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  violet:
    "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  amber: "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  indigo:
    "border-indigo-500/20 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  rose: "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  cyan: "border-cyan-500/20 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  slate: "border-slate-500/20 bg-slate-500/10 text-slate-700 dark:text-slate-300",
};

const DEFAULT_COLOR_CLASS = "border-border/60 bg-muted/40 text-muted-foreground";

export function RouteBadge({ route }: { route: Route }) {
  const skillsQuery = useSkillsQuery();
  const skill = (skillsQuery.data ?? []).find((item) => item.name === route);

  const meta: RouteMeta = skill
    ? { label: skill.label, icon: skill.icon, color: skill.color }
    : (FALLBACK_META[route] ?? {
        label: route,
        icon: "sparkles",
        color: "slate",
      });

  // 直接从模块级 ICONS 查表取稳定的图标组件引用；不要用函数调用的返回值
  // 作为 JSX 标签，否则会被 react-hooks/static-components 规则判定为“渲染期创建组件”。
  const Icon = ICONS[meta.icon] ?? Sparkles;
  const colorClass = COLOR_CLASSES[meta.color] ?? DEFAULT_COLOR_CLASS;

  return (
    <Badge variant="outline" className={cn("gap-1", colorClass)}>
      <Icon className="size-3" />
      {meta.label}
    </Badge>
  );
}
