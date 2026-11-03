"use client";

import { useState } from "react";
import {
  Box,
  ChevronDown,
  ChevronUp,
  Plug,
  RefreshCw,
  Sparkles,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useMcpStatusQuery, useSkillsQuery } from "@/hooks/queries";
import { getErrorMessage } from "@/lib/api";
import type { SkillInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

// 技能种类 → 展示图标与中文标签（面板按 kind 归类，不逐技能解析图标名）
const KIND_META: Record<
  string,
  { label: string; icon: typeof Sparkles }
> = {
  builtin: { label: "内置", icon: Sparkles },
  mcp: { label: "MCP", icon: Wrench },
  custom: { label: "自定义", icon: Box },
};

// 折叠阈值：默认仅展示前 N 项，超出部分点击展开后在滚动区域内查看
const COLLAPSE_COUNT = 3;

function SkillRow({ skill }: { skill: SkillInfo }) {
  const kind = KIND_META[skill.kind] ?? KIND_META.custom;
  const Icon = kind.icon;

  return (
    <li className="rounded-md border border-border/60 bg-background/70 p-2.5">
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-xs font-medium text-foreground">
              {skill.label}
            </span>
            <code className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
              {skill.name}
            </code>
            <Badge
              variant="outline"
              className="ml-auto shrink-0 px-1.5 text-[10px]"
            >
              {kind.label}
            </Badge>
          </div>
          <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-muted-foreground">
            {skill.description}
          </p>
        </div>
      </div>
    </li>
  );
}

// 展开 / 收起更多条目（超出折叠阈值时出现）
function ToggleMore({
  expanded,
  total,
  onToggle,
}: {
  expanded: boolean;
  total: number;
  onToggle: () => void;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      onClick={onToggle}
      className="w-full justify-center text-[11px] text-muted-foreground"
    >
      {expanded ? (
        <>
          <ChevronUp className="size-3" />
          收起
        </>
      ) : (
        <>
          <ChevronDown className="size-3" />
          展开全部 {total} 项
        </>
      )}
    </Button>
  );
}

export function SkillsPanel() {
  const skillsQuery = useSkillsQuery();
  const mcpQuery = useMcpStatusQuery();
  const skills = skillsQuery.data ?? [];
  const mcp = mcpQuery.data;
  const refreshing = skillsQuery.isFetching || mcpQuery.isFetching;
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [mcpExpanded, setMcpExpanded] = useState(false);

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="size-4 text-muted-foreground" />
          技能与工具
        </CardTitle>
        <div className="flex items-center gap-1.5">
          {skillsQuery.data ? (
            <span className="text-[10px] text-muted-foreground">
              {skills.length} 个技能
            </span>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            onClick={() => {
              void skillsQuery.refetch();
              void mcpQuery.refetch();
            }}
            disabled={refreshing}
            aria-label="刷新技能列表"
            title="刷新技能列表"
          >
            <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 px-4 py-4">
        <div className="space-y-2">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            已注册技能
          </h3>
          {skillsQuery.isLoading ? (
            <p className="text-[11px] text-muted-foreground">加载中…</p>
          ) : skillsQuery.isError ? (
            <p className="text-[11px] text-destructive">
              加载失败：{getErrorMessage(skillsQuery.error)}
            </p>
          ) : skills.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">暂无可用技能。</p>
          ) : (
            <div className="space-y-1.5">
              <ul
                className={cn(
                  "space-y-1.5",
                  skillsExpanded &&
                    skills.length > COLLAPSE_COUNT &&
                    "scrollbar-thin max-h-[300px] overflow-y-auto pr-1",
                )}
              >
                {(skillsExpanded ? skills : skills.slice(0, COLLAPSE_COUNT)).map(
                  (skill) => <SkillRow key={skill.name} skill={skill} />,
                )}
              </ul>
              {skills.length > COLLAPSE_COUNT ? (
                <ToggleMore
                  expanded={skillsExpanded}
                  total={skills.length}
                  onToggle={() => setSkillsExpanded((value) => !value)}
                />
              ) : null}
            </div>
          )}
        </div>

        <div className="space-y-2 border-t border-border/60 pt-3">
          <h3 className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            <Plug className="size-3" />
            MCP 工具
          </h3>
          {mcpQuery.isLoading ? (
            <p className="text-[11px] text-muted-foreground">加载中…</p>
          ) : mcpQuery.isError ? (
            <p className="text-[11px] text-destructive">
              加载失败：{getErrorMessage(mcpQuery.error)}
            </p>
          ) : !mcp?.configured ? (
            <p className="text-[11px] leading-5 text-muted-foreground">
              未配置 MCP 服务。把项目根的{" "}
              <code className="rounded bg-muted px-1">mcp.example.json</code>{" "}
              复制为 <code className="rounded bg-muted px-1">mcp.json</code>{" "}
              并填写后重启即可接入。
            </p>
          ) : (
            <div className="space-y-1.5">
              <p className="text-[11px] text-muted-foreground">
                已连接 {mcp.servers.length} 个服务：{mcp.servers.join("、")}
              </p>
              {mcp.error ? (
                <p className="text-[11px] text-destructive">
                  工具加载异常：{mcp.error}
                </p>
              ) : mcp.tools.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">
                  暂未发现可用工具。
                </p>
              ) : (
                <div className="space-y-1.5">
                  <ul
                    className={cn(
                      "space-y-1",
                      mcpExpanded &&
                        mcp.tools.length > COLLAPSE_COUNT &&
                        "scrollbar-thin max-h-[300px] overflow-y-auto pr-1",
                    )}
                  >
                    {(mcpExpanded
                      ? mcp.tools
                      : mcp.tools.slice(0, COLLAPSE_COUNT)
                    ).map((tool) => (
                      <li
                        key={tool.name}
                        className="rounded-md border border-border/60 bg-background/70 px-2 py-1.5"
                      >
                        <span className="text-[11px] font-medium text-foreground">
                          {tool.name}
                        </span>
                        {tool.description ? (
                          <p className="mt-0.5 line-clamp-2 text-[10px] leading-4 text-muted-foreground">
                            {tool.description}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  {mcp.tools.length > COLLAPSE_COUNT ? (
                    <ToggleMore
                      expanded={mcpExpanded}
                      total={mcp.tools.length}
                      onToggle={() => setMcpExpanded((value) => !value)}
                    />
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
