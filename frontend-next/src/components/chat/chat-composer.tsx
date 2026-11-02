"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MAX_MESSAGE_LENGTH } from "@/lib/constants";

export function ChatComposer({
  onSend,
  disabled,
  isSending,
}: {
  onSend: (message: string) => void;
  disabled: boolean;
  isSending: boolean;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    // scrollHeight 不含边框，box-sizing: border-box 下需要补上边框高度。
    const borderSize = element.offsetHeight - element.clientHeight;
    element.style.height = `${Math.min(element.scrollHeight + borderSize, 160)}px`;
  }, [value]);

  function submit() {
    const message = value.trim();
    if (!message || disabled || isSending) return;
    onSend(message);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    // 中文输入法组合期间的回车用于上屏，不应发送消息。
    if (event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  }

  const canSend = value.trim().length > 0 && !disabled && !isSending;
  const nearLimit = value.length > MAX_MESSAGE_LENGTH * 0.9;

  return (
    <div className="border-t border-border/60 bg-card/60 p-3 sm:p-4">
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          maxLength={MAX_MESSAGE_LENGTH}
          disabled={isSending}
          placeholder={
            disabled
              ? "正在加载会话历史…"
              : "输入问题… Enter 发送，Shift + Enter 换行"
          }
          aria-label="消息内容"
          className="max-h-40 min-h-11 resize-none rounded-xl border-border/70 px-3.5 py-2.5 text-sm leading-6"
        />
        <Button
          type="button"
          size="icon-lg"
          onClick={submit}
          disabled={!canSend}
          aria-label="发送消息"
          title="发送消息"
          className="mb-0.5 shrink-0 rounded-xl"
        >
          {isSending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
        </Button>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2 px-1 text-[10px] text-muted-foreground">
        <span>
          {disabled
            ? "正在加载会话历史…"
            : isSending
              ? "Agent 正在处理，请稍候…"
              : "Enter 发送 · Shift + Enter 换行"}
        </span>
        <span
          className={
            nearLimit ? "font-medium text-amber-600 dark:text-amber-400" : ""
          }
        >
          {value.length} / {MAX_MESSAGE_LENGTH}
        </span>
      </div>
    </div>
  );
}
