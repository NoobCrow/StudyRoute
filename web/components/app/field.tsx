import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";

/** A labelled control with an optional hint and an inline, announced error. */
export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={htmlFor} className="text-[13px]">
        {label}
      </Label>
      {children}
      {hint ? (
        <span className="text-muted-foreground text-xs" id={`${htmlFor}-hint`}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="text-destructive text-xs" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
