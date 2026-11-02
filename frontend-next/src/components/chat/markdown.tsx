"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import { safeHttpUrl } from "@/lib/format";

const components: Components = {
  a: ({ href, children }) => {
    const url = safeHttpUrl(href);
    if (!url) return <span>{children}</span>;
    return (
      <a href={url} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  img: ({ src, alt }) => {
    const url = typeof src === "string" ? safeHttpUrl(src) : null;
    if (!url) return null;
    // Markdown 图片来自外部地址，无法预先配置 next/image 的 remotePatterns。
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt={alt ?? ""} loading="lazy" />;
  },
};

export function Markdown({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={safeHttpUrl}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
