"use client";

import { useState, type FormEvent } from "react";
import { Bot, Globe, Library, Loader2, Users } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

type Mode = "login" | "register";

/** 卡片底部的特性条目，保持与主界面卖点一致 */
const FEATURES = [
  { icon: Users, label: "多 Agent 协作" },
  { icon: Library, label: "本地知识库 RAG" },
  { icon: Globe, label: "联网搜索" },
] as const;

/** 未登录时展示的登录 / 注册页；成功后由 assistant-app 切换到主界面。 */
export function AuthScreen() {
  const login = useAuthStore((state) => state.login);
  const register = useAuthStore((state) => state.register);
  const pending = useAuthStore((state) => state.pending);

  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);

    const trimmed = username.trim();
    if (mode === "register") {
      if (trimmed.length < 2) {
        setError("用户名至少 2 个字符");
        return;
      }
      // 与后端 RegisterRequest 的 pattern 保持一致，提前拦截并给出友好提示
      if (!/^[\p{L}\p{N}._@+-]+$/u.test(trimmed)) {
        setError("用户名只能包含中英文、数字及 . _ @ + - 符号");
        return;
      }
    }
    if (password.length < 6) {
      setError("密码至少 6 位");
      return;
    }

    try {
      if (mode === "login") {
        await login(trimmed, password);
      } else {
        await register(trimmed, password);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  const isLogin = mode === "login";

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden">
      {/* 背景装饰：细网格 + 顶部柔光，营造轻盈的层次而不喧宾夺主 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 [background-image:linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] [background-size:56px_56px] opacity-40 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[40rem] -translate-x-1/2 rounded-full bg-foreground/[0.04] blur-3xl"
      />

      <div className="relative flex justify-end px-4 py-3">
        <ThemeToggle />
      </div>

      <main className="relative flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm">
          {/* 品牌区：去掉彩色渐变，回归黑白灰的克制表达 */}
          <div className="mb-10 flex flex-col items-center text-center">
            <div className="grid size-12 place-items-center rounded-xl border border-border bg-card text-foreground shadow-sm">
              <Bot className="size-6" />
            </div>
            <h1 className="mt-5 text-2xl font-semibold tracking-tight">
              Agent 智能助手
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {isLogin ? "欢迎回来，登录后继续对话" : "创建账号，开启智能协作"}
            </p>
          </div>

          <div className="rounded-2xl border border-border/70 bg-card/70 p-6 shadow-xl shadow-black/[0.03] backdrop-blur-sm">
            {/* 登录 / 注册切换：下划线式 Tab，比分段控件更轻 */}
            <div className="mb-6 grid grid-cols-2 gap-6 border-b border-border">
              {(["login", "register"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => switchMode(value)}
                  className={cn(
                    "-mb-px border-b-2 pb-2.5 text-sm font-medium transition-colors",
                    mode === value
                      ? "border-foreground text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {value === "login" ? "登录" : "注册"}
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label
                  htmlFor="username"
                  className="text-xs font-medium text-muted-foreground"
                >
                  用户名
                </label>
                <Input
                  id="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="请输入用户名"
                  autoComplete="username"
                  disabled={pending}
                  className="h-10 bg-transparent"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="password"
                  className="text-xs font-medium text-muted-foreground"
                >
                  密码
                </label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="至少 6 位"
                  autoComplete={isLogin ? "current-password" : "new-password"}
                  disabled={pending}
                  className="h-10 bg-transparent"
                />
              </div>

              {error && (
                <p className="rounded-md border border-destructive/20 bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                disabled={pending || !username || !password}
                className="mt-2 h-10 w-full rounded-lg text-sm font-medium"
              >
                {pending && <Loader2 className="size-4 animate-spin" />}
                {isLogin ? "登录" : "注册并登录"}
              </Button>
            </form>
          </div>

          {/* 特性说明：一行小字带图标，替代原先副标题里的堆砌文案 */}
          <div className="mt-8 flex items-center justify-center gap-5 text-[11px] text-muted-foreground/80">
            {FEATURES.map(({ icon: Icon, label }) => (
              <span key={label} className="flex items-center gap-1.5">
                <Icon className="size-3.5" />
                {label}
              </span>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
