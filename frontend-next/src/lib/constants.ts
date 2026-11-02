/** 与后端 app/config.py 对齐的前端常量。 */

export const DEFAULT_SESSION_ID = "default";

export const MAX_SESSION_LENGTH = 100;

export const MAX_MESSAGE_LENGTH = 8000;

/** 后端 MAX_UPLOAD_MB 默认值，用于上传前即时校验。 */
export const MAX_UPLOAD_MB = 20;

/** 与后端 ALLOWED_EXTENSIONS 保持一致。 */
export const ACCEPTED_FILE_EXTENSIONS = [
  ".pdf",
  ".md",
  ".markdown",
  ".txt",
  ".docx",
  ".pptx",
  ".xlsx",
  ".png",
  ".jpg",
  ".jpeg",
] as const;

export const ACCEPT_ATTRIBUTE = ACCEPTED_FILE_EXTENSIONS.join(",");

export const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  md: "Markdown",
  markdown: "Markdown",
  txt: "TXT",
  docx: "Word",
  pptx: "PPT",
  xlsx: "Excel",
  png: "图片",
  jpg: "图片",
  jpeg: "图片",
};

export const SUGGESTIONS = [
  "你能做什么？请简单介绍一下。",
  "搜索最近 AI 领域的重要新闻",
  "帮我写一个 Python 快速排序的示例",
] as const;

export const KNOWLEDGE_SUGGESTION = "根据知识库总结一下我上传的文档";
