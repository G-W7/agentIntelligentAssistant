import { BookOpen, MessageSquare, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Route } from "@/lib/types";

const ROUTE_META: Record<
  Route,
  { label: string; icon: typeof BookOpen; className: string }
> = {
  rag: {
    label: "知识库",
    icon: BookOpen,
    className:
      "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  search: {
    label: "联网搜索",
    icon: Search,
    className:
      "border-sky-500/20 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  chat: {
    label: "通用对话",
    icon: MessageSquare,
    className:
      "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
};

export function RouteBadge({ route }: { route: Route }) {
  const meta = ROUTE_META[route];
  const Icon = meta.icon;

  return (
    <Badge variant="outline" className={cn("gap-1", meta.className)}>
      <Icon className="size-3" />
      {meta.label}
    </Badge>
  );
}
