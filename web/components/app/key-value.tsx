import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A label and its value on one line; rows are separated by a hairline. */
export function KV({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-x-4 gap-y-1 border-t py-2.5 text-sm first:border-t-0 sm:grid-cols-[var(--kv-label)_1fr]",
        wide ? "[--kv-label:13rem]" : "[--kv-label:10rem]",
      )}
    >
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function KVList({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={className}>{children}</dl>;
}
