import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

const TONE = {
  ok: "border-success-soft-foreground/25 bg-success-soft text-success-soft-foreground",
  warn: "border-warning-soft-foreground/25 bg-warning-soft text-warning-soft-foreground",
  danger: "border-danger-soft-foreground/25 bg-danger-soft text-danger-soft-foreground",
  info: "border-info-soft-foreground/25 bg-info-soft text-info-soft-foreground",
} as const;

/** A message in a tinted box. Danger notices are announced to screen readers as alerts. */
export function Notice({
  tone,
  title,
  children,
  className,
}: {
  tone: keyof typeof TONE;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <Alert role={tone === "danger" ? "alert" : "status"} className={cn(TONE[tone], className)}>
      {title ? <AlertTitle>{title}</AlertTitle> : null}
      {children ? <AlertDescription className="text-inherit">{children}</AlertDescription> : null}
    </Alert>
  );
}

/** What went wrong, from the RFC 7807 problem the API sent, with an optional Retry. */
export function ErrorNotice({ error, onRetry }: { error: Error | null; onRetry?: () => void }) {
  if (!error) return null;
  const retry = onRetry ? (
    <Button type="button" variant="outline" size="sm" className="bg-card mt-2" onClick={onRetry}>
      Retry
    </Button>
  ) : null;
  if (error instanceof ApiError) {
    return (
      <Notice tone="danger" title={`${error.title} (${error.code})`}>
        <span>{error.message}</span>
        {error.retryAfter ? <span> Try again in {error.retryAfter} seconds.</span> : null}
        {error.requestId ? (
          <span className="text-xs opacity-80"> Request {error.requestId}</span>
        ) : null}
        {retry ? <div>{retry}</div> : null}
      </Notice>
    );
  }
  return (
    <Notice tone="danger" title="Something went wrong">
      {error.message}
      {retry ? <div>{retry}</div> : null}
    </Notice>
  );
}
