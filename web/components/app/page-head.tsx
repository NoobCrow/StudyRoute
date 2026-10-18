import type { ReactNode } from "react";

export function PageHead({
  title,
  children,
  actions,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1.5">
        <h1>{title}</h1>
        <span
          aria-hidden="true"
          className="bg-primary animate-grow-x block h-1 w-10 origin-left rounded-full"
        />
        {children ? <p className="text-muted-foreground max-w-2xl">{children}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
