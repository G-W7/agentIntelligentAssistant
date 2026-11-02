"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

function toggleTheme() {
  const root = document.documentElement;
  const dark = root.classList.toggle("dark");
  try {
    localStorage.setItem("theme", dark ? "dark" : "light");
  } catch {
    // 隐私模式下 localStorage 可能不可用，忽略即可。
  }
}

export function ThemeToggle() {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      onClick={toggleTheme}
      title="切换深色模式"
      aria-label="切换深色模式"
    >
      <Sun className="hidden size-4 dark:block" />
      <Moon className="size-4 dark:hidden" />
    </Button>
  );
}
