import { Suspense } from "react";

import { AssistantApp } from "@/components/assistant-app";

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          正在加载…
        </div>
      }
    >
      <AssistantApp />
    </Suspense>
  );
}
